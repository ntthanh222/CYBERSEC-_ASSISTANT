"""Password strength analysis - stateless by construction.

Security invariants (each has a dedicated test in
``backend/tests/test_password_check.py``):

* The password is never persisted. No table in this application has a column
  for it, and no scan-history row is written by a password check.
* The password is never logged. Nothing in this module or its route logs the
  request body, and no exception raised here embeds the value.
* The password is never used as a metric label. Only the resulting strength
  bucket - one of four fixed strings - is counted.
* The password is never echoed back. The response carries derived facts only.
* No network call is made: the common-password check runs against a bundled
  list, so the value never leaves the process.

The analysis itself is deliberately holistic rather than a checklist: a long
passphrase of lowercase words scores well without containing a symbol, which is
what modern guidance (NIST SP 800-63B) actually recommends.
"""
import math
import re
from dataclasses import dataclass
from typing import Final

#: Offline attack rate assumed when estimating crack time: a well-resourced
#: attacker against a fast hash. Deliberately pessimistic - the estimate is a
#: floor, not a promise.
GUESSES_PER_SECOND: Final = 1e10

STRENGTH_LEVELS: Final = ("weak", "medium", "strong", "very_strong")

#: Bundled list of the most abused passwords and their obvious mutations. Kept
#: short on purpose: it exists to catch the catastrophic cases, and a larger
#: corpus belongs in a dedicated breach-data service, not in application code.
COMMON_PASSWORDS: Final = frozenset(
    {
        "123456", "12345678", "123456789", "1234567890", "12345", "1234567",
        "password", "password1", "password123", "passw0rd", "p@ssw0rd",
        "qwerty", "qwerty123", "qwertyuiop", "asdfghjkl", "zxcvbnm",
        "abc123", "111111", "000000", "123123", "654321", "121212",
        "iloveyou", "admin", "administrator", "root", "toor", "letmein",
        "welcome", "welcome1", "monkey", "dragon", "sunshine", "princess",
        "football", "baseball", "superman", "batman", "trustno1", "starwars",
        "master", "shadow", "michael", "jennifer", "jordan", "hunter",
        "freedom", "whatever", "qazwsx", "1q2w3e4r", "1qaz2wsx", "zaq12wsx",
        "changeme", "default", "guest", "test", "test123", "demo", "temp",
        "secret", "login", "pass", "access", "flower", "hello", "charlie",
        "matkhau", "matkhau123", "vietnam", "hanoi", "saigon",
    }
)

_KEYBOARD_ROWS: Final = (
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "1234567890",
    "!@#$%^&*()",
)

_SPECIAL_PATTERN: Final = re.compile(r"[^A-Za-z0-9]")
_LEET_TABLE: Final = str.maketrans(
    {"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)


@dataclass(frozen=True)
class CharacterClasses:
    lowercase: bool
    uppercase: bool
    digits: bool
    special: bool

    @property
    def count(self) -> int:
        return sum((self.lowercase, self.uppercase, self.digits, self.special))

    @property
    def pool_size(self) -> int:
        size = 0
        if self.lowercase:
            size += 26
        if self.uppercase:
            size += 26
        if self.digits:
            size += 10
        if self.special:
            size += 33
        return size or 1


def analyse_classes(password: str) -> CharacterClasses:
    return CharacterClasses(
        lowercase=any(character.islower() for character in password),
        uppercase=any(character.isupper() for character in password),
        digits=any(character.isdigit() for character in password),
        special=bool(_SPECIAL_PATTERN.search(password)),
    )


def longest_repeat_run(password: str) -> int:
    """Length of the longest run of one repeated character."""
    longest = 0
    run = 0
    previous = None
    for character in password:
        run = run + 1 if character == previous else 1
        previous = character
        longest = max(longest, run)
    return longest


def has_repeated_block(password: str) -> bool:
    """True when the password is a short block repeated (``abcabcabc``)."""
    lowered = password.lower()
    length = len(lowered)
    for block in range(1, length // 2 + 1):
        if length % block == 0 and lowered[:block] * (length // block) == lowered:
            return True
    return False


def longest_sequential_run(password: str) -> int:
    """Longest ascending/descending alphabet, digit or keyboard-row run."""
    lowered = password.lower()
    longest = 0

    # Ordinal sequences: abc / cba / 123 / 321.
    for direction in (1, -1):
        run = 1
        for index in range(1, len(lowered)):
            if ord(lowered[index]) - ord(lowered[index - 1]) == direction:
                run += 1
                longest = max(longest, run)
            else:
                run = 1

    # Keyboard-adjacency sequences.
    for row in _KEYBOARD_ROWS:
        for start in range(len(row)):
            for end in range(start + 3, len(row) + 1):
                fragment = row[start:end]
                if fragment in lowered or fragment[::-1] in lowered:
                    longest = max(longest, len(fragment))
    return longest


def is_common(password: str) -> bool:
    """True for a known-common password, including simple leet mutations."""
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return True
    # Strip a trailing digit/symbol run ("password123!" -> "password").
    trimmed = re.sub(r"[0-9!@#$%^&*_.-]+$", "", lowered)
    if trimmed and trimmed in COMMON_PASSWORDS:
        return True
    de_leeted = lowered.translate(_LEET_TABLE)
    return de_leeted in COMMON_PASSWORDS


def estimate_entropy_bits(password: str) -> float:
    """Rough entropy estimate, discounted for structure the attacker can guess.

    This is intentionally not a full pattern-matching estimator like zxcvbn: it
    is a transparent, explainable number. It errs low, never high.
    """
    if not password:
        return 0.0
    classes = analyse_classes(password)
    raw = len(password) * math.log2(classes.pool_size)

    # Repeated characters and predictable runs add far less than their length
    # suggests, so discount the portion of the password they account for.
    repeat_run = longest_repeat_run(password)
    sequential_run = longest_sequential_run(password)
    predictable = max(0, repeat_run - 1) + max(0, sequential_run - 1)
    effective_length = max(1, len(password) - predictable * 0.75)
    discounted = effective_length * math.log2(classes.pool_size)

    entropy = min(raw, discounted)
    if has_repeated_block(password):
        entropy *= 0.5
    return round(entropy, 2)


def _score_from_entropy(entropy: float) -> int:
    if entropy < 28:
        return 0
    if entropy < 40:
        return 1
    if entropy < 60:
        return 2
    if entropy < 80:
        return 3
    return 4


def format_crack_time(entropy: float) -> str:
    """Human estimate of an offline brute-force at :data:`GUESSES_PER_SECOND`."""
    seconds = (2 ** min(entropy, 256)) / 2 / GUESSES_PER_SECOND
    if seconds < 1:
        return "dưới một giây"
    for limit, divisor, unit in (
        (60, 1, "giây"),
        (3600, 60, "phút"),
        (86400, 3600, "giờ"),
        (2_592_000, 86400, "ngày"),
        (31_536_000, 2_592_000, "tháng"),
        (3_153_600_000, 31_536_000, "năm"),
    ):
        if seconds < limit:
            value = int(seconds / divisor)
            return f"khoảng {value} {unit}"
    centuries = seconds / 3_153_600_000
    if centuries > 1e6:
        return "gần như vô hạn với tốc độ tấn công hiện tại"
    return f"khoảng {int(centuries)} thế kỷ"


def analyse(password: str) -> dict:
    """Analyse ``password`` and return derived facts only.

    The returned dictionary never contains the password or any substring of it.
    """
    length = len(password)
    classes = analyse_classes(password)
    entropy = estimate_entropy_bits(password)
    repeat_run = longest_repeat_run(password)
    sequential_run = longest_sequential_run(password)
    repeated_block = has_repeated_block(password)
    common = is_common(password)

    score = _score_from_entropy(entropy)
    warnings: list[str] = []

    if common:
        score = 0
        warnings.append(
            "Đây là mật khẩu phổ biến (hoặc một biến thể đơn giản của nó) và "
            "sẽ bị đoán ra gần như ngay lập tức."
        )
    if length < 8:
        score = min(score, 1)
        warnings.append("Dưới 8 ký tự là quá ngắn bất kể độ phức tạp.")
    if repeat_run >= 3:
        score = min(score, 2)
        warnings.append(f"Chứa chuỗi {repeat_run} ký tự giống hệt nhau liên tiếp.")
    if sequential_run >= 4:
        score = min(score, 2)
        warnings.append(
            f"Chứa một chuỗi có thể đoán trước gồm {sequential_run} ký tự "
            "(bảng chữ cái, chữ số hoặc hàng phím)."
        )
    if repeated_block and length > 3:
        score = min(score, 1)
        warnings.append("Mật khẩu là một khối ngắn được lặp lại, không tăng thêm nhiều độ mạnh.")

    strength = STRENGTH_LEVELS[min(score, 4) if score < 4 else 3]
    if score == 4:
        strength = "very_strong"
    elif score == 3:
        strength = "strong"
    elif score == 2:
        strength = "medium"
    else:
        strength = "weak"

    return {
        "score": score,
        "strength": strength,
        "length": length,
        "entropy_bits": entropy,
        "crack_time": format_crack_time(entropy),
        "has_lowercase": classes.lowercase,
        "has_uppercase": classes.uppercase,
        "has_digits": classes.digits,
        "has_special": classes.special,
        "character_classes": classes.count,
        "longest_repeat_run": repeat_run,
        "longest_sequential_run": sequential_run,
        "has_repeated_block": repeated_block,
        "is_common": common,
        "warnings": warnings,
        "recommendations": build_recommendations(
            score=score,
            length=length,
            classes=classes,
            common=common,
            repeat_run=repeat_run,
            sequential_run=sequential_run,
        ),
    }


def build_recommendations(
    *,
    score: int,
    length: int,
    classes: CharacterClasses,
    common: bool,
    repeat_run: int,
    sequential_run: int,
) -> list[str]:
    recommendations: list[str] = []
    if common:
        recommendations.append("Chọn một mật khẩu không nằm trong bất kỳ danh sách mật khẩu phổ biến nào.")
    if length < 12:
        recommendations.append(
            "Nên dùng ít nhất 12 ký tự; độ dài đóng góp nhiều hơn bất kỳ yếu tố nào khác."
        )
    if length < 16 and classes.count <= 2:
        recommendations.append(
            "Dùng một cụm mật khẩu gồm bốn từ không liên quan trở lên - dễ nhớ hơn và "
            "khó bẻ khóa hơn một chuỗi ngắn phức tạp."
        )
    if repeat_run >= 3:
        recommendations.append("Tránh lặp lại cùng một ký tự nhiều lần liên tiếp.")
    if sequential_run >= 4:
        recommendations.append("Tránh các chuỗi phím liền kề và các dãy chữ cái hoặc số liên tiếp.")
    if classes.count <= 2 and length < 16:
        recommendations.append("Kết hợp thêm một loại ký tự khác, hoặc làm cho mật khẩu dài hơn đáng kể.")
    if score >= 3:
        recommendations.append(
            "Lưu mật khẩu này trong trình quản lý mật khẩu và không bao giờ dùng lại cho tài khoản khác."
        )
    recommendations.append("Bật xác thực đa yếu tố ở mọi nơi sử dụng mật khẩu này.")
    return recommendations


#: Static advice keyed by strength bucket. Served by the guidance endpoint so a
#: client-side checker can render the same wording without sending anything.
GUIDANCE: Final[dict[str, dict[str, object]]] = {
    "weak": {
        "strength": "weak",
        "headline": "Mật khẩu này sẽ không chống chọi được một cuộc tấn công offline.",
        "feedback": (
            "Mật khẩu ngắn, phổ biến hoặc có mẫu hình rõ ràng sẽ bị bẻ khóa trong vài giây "
            "khi cơ sở dữ liệu mật khẩu bị đánh cắp."
        ),
        "recommendations": [
            "Dùng ít nhất 12 ký tự, tốt nhất là một cụm mật khẩu gồm bốn từ không liên quan.",
            "Tránh dùng từ điển, tên riêng, ngày tháng và các chuỗi phím liền kề.",
            "Không bao giờ dùng lại một mật khẩu cho nhiều tài khoản.",
        ],
    },
    "medium": {
        "strength": "medium",
        "headline": "Chấp nhận được cho tài khoản ít quan trọng, không phù hợp cho bất cứ điều gì quan trọng.",
        "feedback": (
            "Mật khẩu này chống được việc đoán thông thường nhưng không chống được một cuộc "
            "tấn công offline có chủ đích nhắm vào hàm băm nhanh."
        ),
        "recommendations": [
            "Tăng độ dài trước khi tăng độ phức tạp.",
            "Loại bỏ mọi chuỗi có thể đoán trước hoặc khối lặp lại.",
            "Bật xác thực đa yếu tố.",
        ],
    },
    "strong": {
        "strength": "strong",
        "headline": "Đủ mạnh cho hầu hết các tài khoản.",
        "feedback": "Độ dài và độ đa dạng tốt, không có điểm yếu cấu trúc rõ ràng.",
        "recommendations": [
            "Lưu mật khẩu này trong trình quản lý mật khẩu thay vì ghi nhớ.",
            "Giữ mật khẩu này riêng cho một tài khoản duy nhất.",
            "Bật xác thực đa yếu tố.",
        ],
    },
    "very_strong": {
        "strength": "very_strong",
        "headline": "Rất mạnh.",
        "feedback": "Tấn công vét cạn không phải là mối đe dọa thực tế đối với mật khẩu này.",
        "recommendations": [
            "Bảo vệ mật khẩu này bằng trình quản lý mật khẩu và một mật khẩu chính mạnh.",
            "Lừa đảo (phishing), chứ không phải bẻ khóa, mới là rủi ro thực tế hiện nay - hãy xác minh trang web trước khi đăng nhập.",
            "Bật xác thực đa yếu tố.",
        ],
    },
}
