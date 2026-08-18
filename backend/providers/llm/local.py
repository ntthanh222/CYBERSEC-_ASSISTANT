"""Local knowledge provider - the honest fallback.

This is *not* a simulated LLM. It is a small, hand-written knowledge base of
defensive security guidance that answers a bounded set of questions and openly
says when it cannot. It reports ``provider="local"`` so a client can never
mistake its output for a model's, per blueprint 16.12 ("Nếu response đến từ
rule ... Không gắn nhãn Gemini").

It also serves Fast Mode, where the blueprint requires that greetings and short
definitional questions are answered without calling a paid model at all.
"""
from typing import Final, Optional, Sequence

from backend.providers.llm.base import BaseLLMProvider, LLMMessage, LLMResult
from backend.services.intent import Intent, classify
from backend.services.rag.response_language import wants_english

PROVIDER_NAME: Final = "local"

# Vietnamese is the platform default for every canned answer below; the
# _EN variants are only used when the user's message explicitly asks for an
# English reply (see services.rag.response_language.wants_english).

_UNKNOWN_ANSWER_VI: Final = (
    "Tôi chưa tìm thấy thông tin đủ đáng tin cậy trong Knowledge Base để trả "
    "lời câu hỏi này.\n\n"
    "Ở chế độ FAST, hệ thống ưu tiên RAG cục bộ và không gọi Gemini nhằm tiết "
    "kiệm quota và tránh đưa ra câu trả lời không có căn cứ. Đây là phản hồi "
    "từ built-in local knowledge base, không phải từ mô hình AI bên ngoài.\n\n"
    "Bạn có thể:\n"
    "• bổ sung tài liệu vào Knowledge Base;\n"
    "• thử một câu hỏi khác;\n"
    "• hoặc dùng DEEP nếu cần Gemini phân tích sâu hơn.\n\n"
    "Security Toolkit (URL Scanner, Password Checker, CVE Lookup) luôn trả về "
    "dữ liệu thật, không phụ thuộc vào bước này."
)

_UNKNOWN_ANSWER_EN: Final = (
    "I do not have a local answer for that. This response came from the "
    "built-in local knowledge base, not from an external AI model - see this "
    "message's routing_reason/external_provider_configured metadata for why "
    "(Fast Mode intentionally skips the external model for simple questions "
    "to save quota; it may also be that no external provider is configured "
    "at all). I will not guess. The Security Toolkit (URL Scanner, Password "
    "Checker and CVE Lookup) always returns real data regardless."
)

_GREETING_ANSWER_VI: Final = (
    "Xin chào. Tôi là CyberSec Assistant. Tôi có thể hỗ trợ bạn về các chủ đề "
    "bảo mật phòng thủ: tìm hiểu về một CVE, kiểm tra một URL đáng ngờ, tăng "
    "cường bảo mật hệ thống (hardening), và xem tình trạng hoạt động cùng "
    "lịch sử quét của nền tảng. Bạn muốn tìm hiểu điều gì?"
)

_GREETING_ANSWER_EN: Final = (
    "Hello. I am the CyberSec Assistant. I can help with defensive security "
    "topics: understanding a CVE, reviewing a suspicious URL, hardening "
    "practices, and reading the platform's own health and scan history. "
    "What would you like to look at?"
)

_PASSWORD_ANSWER_VI: Final = (
    "Tôi không đánh giá mật khẩu trong khung chat, và bạn không nên dán mật "
    "khẩu thật vào bất kỳ cuộc trò chuyện nào - kể cả cuộc trò chuyện này.\n\n"
    "Hãy dùng công cụ Password Checker thay thế. Công cụ này chấm điểm dựa "
    "trên độ dài, độ đa dạng ký tự, các mẫu lặp/liên tiếp và danh sách mật "
    "khẩu phổ biến đã biết.\n\n"
    "Hướng dẫn chung:\n"
    "- Độ dài quan trọng hơn ký tự đặc biệt; nên dùng cụm 4+ từ không liên "
    "quan nhau (passphrase).\n"
    "- Không dùng lại cùng một mật khẩu cho nhiều tài khoản.\n"
    "- Dùng trình quản lý mật khẩu để tạo và lưu trữ mật khẩu riêng biệt.\n"
    "- Bật xác thực đa yếu tố (MFA) ở bất cứ nơi nào có hỗ trợ."
)

_PASSWORD_ANSWER_EN: Final = (
    "I do not evaluate passwords in chat, and you should not paste a real "
    "password into any conversation - including this one.\n\n"
    "Use the Password Checker tool instead. It scores length, character "
    "variety, repeated and sequential patterns, and known-common passwords.\n\n"
    "General guidance:\n"
    "- Length matters more than symbol soup; aim for a passphrase of 4+ "
    "unrelated words.\n"
    "- Never reuse a password across accounts.\n"
    "- Use a password manager to generate and store unique credentials.\n"
    "- Turn on multi-factor authentication wherever it is offered."
)

_URL_ANSWER_VI: Final = (
    "Để đánh giá một đường link, hãy dùng công cụ URL Scanner thay vì mở nó "
    "trực tiếp. Scanner sẽ phân giải hostname, từ chối các mục tiêu trên "
    "mạng nội bộ, đi theo một số lượng redirect giới hạn và báo cáo các phát "
    "hiện quyết định điểm rủi ro.\n\n"
    "Những dấu hiệu nên kiểm tra bằng mắt trước:\n"
    "- Hostname chỉ *chứa* tên thương hiệu chứ không phải chính thương hiệu "
    "đó.\n"
    "- Punycode/IDN homograph (địa chỉ bắt đầu bằng `xn--`).\n"
    "- Thông tin đăng nhập nhúng trước phần host (`https://user:pass@host`).\n"
    "- Địa chỉ IP trần thay vì tên miền, hoặc cổng (port) bất thường.\n"
    "- Không có HTTPS trên một trang yêu cầu đăng nhập."
)

_URL_ANSWER_EN: Final = (
    "To assess a link, use the URL Scanner tool rather than opening it. The "
    "scanner resolves the hostname, refuses targets on internal networks, "
    "follows a bounded number of redirects and reports the findings that drive "
    "its risk score.\n\n"
    "Signals worth checking by eye first:\n"
    "- A hostname that merely *contains* a brand name rather than being it.\n"
    "- Punycode/IDN homographs (an address starting with `xn--`).\n"
    "- Credentials embedded before the host (`https://user:pass@host`).\n"
    "- A bare IP address instead of a domain, or an unusual port.\n"
    "- No HTTPS on a page that asks for a login."
)

_CVE_ANSWER_VI: Final = (
    "Hãy dùng công cụ CVE Lookup cho một mã CVE cụ thể - công cụ này lấy dữ "
    "liệu từ NVD API công khai và báo cáo điểm CVSS, mức độ nghiêm trọng, "
    "vector tấn công, các sản phẩm bị ảnh hưởng và tài liệu tham khảo, kèm "
    "theo thông tin liệu kết quả có đến từ cache hay không.\n\n"
    "Khi đánh giá một CVE, điểm số không phải là yếu tố duy nhất: hãy kết "
    "hợp với việc thành phần bị ảnh hưởng có thực sự bị lộ diện trong môi "
    "trường của bạn hay không, đã có bản vá hay chưa, và đã ghi nhận khai "
    "thác trong thực tế hay chưa."
)

_CVE_ANSWER_EN: Final = (
    "Use the CVE Lookup tool for a specific identifier - it fetches the record "
    "from the public NVD API and reports the CVSS score, severity, vector, "
    "affected products and references, plus whether the answer came from "
    "cache.\n\n"
    "When triaging a CVE, the score alone is not the priority: combine it with "
    "whether the affected component is actually exposed in your environment, "
    "whether a patch exists, and whether exploitation has been observed."
)

_DEFINITIONS_VI: Final[dict[tuple[str, ...], str]] = {
    ("cvss",): (
        "CVSS (Common Vulnerability Scoring System) là một chuẩn mở để đánh "
        "giá mức độ nghiêm trọng của lỗ hổng theo thang điểm 0.0-10.0. Điểm "
        "cơ bản (base score) mô tả các đặc tính nội tại như vector tấn công, "
        "quyền yêu cầu và tác động đến tính bảo mật, toàn vẹn và sẵn sàng của "
        "dữ liệu. Các mức: 0.1-3.9 thấp, 4.0-6.9 trung bình, 7.0-8.9 cao, "
        "9.0-10.0 nghiêm trọng."
    ),
    ("ssrf", "server-side request forgery"): (
        "SSRF (Server-Side Request Forgery) là lỗ hổng cho phép kẻ tấn công "
        "khiến server gửi yêu cầu HTTP đến một mục tiêu do kẻ tấn công chọn - "
        "thường là các địa chỉ nội bộ mà kẻ tấn công không thể truy cập trực "
        "tiếp, ví dụ 127.0.0.1 hoặc endpoint metadata của cloud.\n\n"
        "Cách phát hiện: giám sát log outbound bất thường từ ứng dụng tới dải "
        "IP private/loopback/link-local (10.0.0.0/8, 127.0.0.0/8, "
        "169.254.169.254...), đặt cảnh báo WAF/IDS cho request có URL do "
        "người dùng cung cấp trỏ tới các dải đó, và kiểm thử với payload URL "
        "nội bộ/redirect trong pentest.\n\n"
        "Cách phòng chống: chỉ cho phép http/https, phân giải hostname và từ "
        "chối các địa chỉ private, loopback, link-local và metadata, xác "
        "thực lại sau mỗi lần redirect, giới hạn timeout và kích thước phản "
        "hồi."
    ),
    ("phishing",): (
        "Phishing là kỹ thuật tấn công phi kỹ thuật (social engineering) giả "
        "mạo một bên đáng tin cậy để lừa nạn nhân tiết lộ thông tin đăng nhập "
        "hoặc chạy một tệp/tác vụ nào đó. Cách phòng chống hiệu quả: dùng MFA "
        "chống phishing, kiểm tra domain gửi thay vì chỉ tin vào tên hiển "
        "thị, và không bao giờ đăng nhập qua một đường link nhận được trong "
        "tin nhắn."
    ),
    ("xss", "cross-site scripting"): (
        "XSS (Cross-Site Scripting) là việc chèn mã script do kẻ tấn công "
        "kiểm soát vào một trang mà người dùng khác xem. Cách phòng chống: "
        "mã hóa output theo đúng ngữ cảnh, coi mọi dữ liệu người dùng nhập "
        "vào là không đáng tin khi render, dùng Content-Security-Policy chặt "
        "chẽ, và tránh gán trực tiếp vào innerHTML mà không lọc dữ liệu."
    ),
    ("mfa", "multi-factor", "2fa", "xac thuc da yeu to", "xác thực đa yếu tố"): (
        "Xác thực đa yếu tố (MFA) yêu cầu nhiều hơn một loại bằng chứng để "
        "đăng nhập. Không phải yếu tố nào cũng an toàn như nhau: security "
        "key phần cứng và passkey chống được phishing, push notification dễ "
        "bị tấn công MFA fatigue, còn mã SMS dễ bị tấn công SIM swap."
    ),
    ("zero trust", "zero-trust"): (
        "Zero Trust là kiến trúc bảo mật không còn coi vị trí mạng là yếu tố "
        "cấp quyền. Mọi yêu cầu đều được xác thực và cấp quyền dựa trên bản "
        "thân nó, quyền truy cập theo nguyên tắc tối thiểu (least-privilege) "
        "và có giới hạn thời gian, với giả định rằng mạng nội bộ đã bị xâm "
        "nhập."
    ),
    ("sql injection", "sqli", "sql-injection"): (
        "SQL Injection là lỗ hổng xảy ra khi dữ liệu người dùng nhập vào "
        "được ghép trực tiếp vào câu lệnh SQL mà không qua kiểm soát, cho "
        "phép kẻ tấn công thay đổi logic truy vấn để đọc, sửa hoặc xóa dữ "
        "liệu ngoài ý muốn, thậm chí bỏ qua xác thực đăng nhập.\n\n"
        "Cách phòng chống:\n"
        "- Luôn dùng câu lệnh tham số hóa (parameterized query) hoặc "
        "prepared statement, không nối chuỗi SQL thủ công.\n"
        "- Dùng ORM an toàn và kiểm tra kỹ mọi truy vấn động (dynamic SQL).\n"
        "- Áp dụng nguyên tắc quyền tối thiểu cho tài khoản kết nối "
        "database.\n"
        "- Kiểm tra và chuẩn hóa (validate/sanitize) dữ liệu đầu vào ở tầng "
        "ứng dụng như một lớp phòng thủ bổ sung."
    ),
    ("command injection", "os command injection"): (
        "Command Injection là lỗ hổng khi ứng dụng truyền dữ liệu người dùng "
        "chưa được kiểm soát vào một lệnh hệ điều hành (shell), cho phép kẻ "
        "tấn công thực thi lệnh tùy ý trên server. Phòng chống: tránh gọi "
        "shell trực tiếp với input người dùng, dùng API gọi tiến trình theo "
        "danh sách tham số (không qua shell), và whitelist nghiêm ngặt các "
        "giá trị đầu vào được phép."
    ),
    ("csrf", "cross-site request forgery"): (
        "CSRF (Cross-Site Request Forgery) là lỗ hổng khiến trình duyệt của "
        "nạn nhân, đang đăng nhập sẵn, bị lừa gửi một yêu cầu không mong "
        "muốn đến ứng dụng. Phòng chống: dùng CSRF token gắn theo phiên, "
        "thuộc tính cookie SameSite, và xác thực lại cho các hành động nhạy "
        "cảm."
    ),
    ("ransomware",): (
        "Khi phát hiện ransomware, hãy hành động theo thứ tự sau:\n"
        "1. Cách ly ngay thiết bị bị nhiễm khỏi mạng (rút cáp mạng/tắt "
        "Wi-Fi) để chặn lây lan, nhưng không tắt máy nếu cần thu thập bằng "
        "chứng.\n"
        "2. Xác định phạm vi ảnh hưởng qua Assets Inventory và Attack Graph, "
        "và mở một Incident trong Incidents & Tasks để theo dõi quá trình "
        "xử lý.\n"
        "3. Không tự ý trả tiền chuộc; liên hệ đội ứng cứu sự cố (CSIRT) và "
        "cấp quản lý theo quy trình playbook.\n"
        "4. Khôi phục dữ liệu từ bản sao lưu sạch (backup) đã được kiểm tra, "
        "sau khi xác nhận hệ thống đã được làm sạch.\n"
        "5. Ghi lại toàn bộ dòng thời gian sự cố (Timeline) và cập nhật "
        "Reports Center sau khi xử lý xong để rút kinh nghiệm."
    ),
    ("mitre att&ck", "mitre attack", "att&ck"): (
        "MITRE ATT&CK là một cơ sở tri thức công khai, mô tả các chiến thuật "
        "(tactics) và kỹ thuật (techniques) mà kẻ tấn công thực sự sử dụng "
        "trong thực tế, được tổ chức theo từng giai đoạn của một cuộc tấn "
        "công (trinh sát, truy cập ban đầu, duy trì quyền truy cập, leo "
        "thang đặc quyền, v.v.). Trong hệ thống này, MITRE Matrix dùng để "
        "ánh xạ các Incident và IOC vào đúng kỹ thuật ATT&CK tương ứng, giúp "
        "chuẩn hóa cách mô tả và phân tích tấn công."
    ),
    ("csp", "content security policy", "content-security-policy"): (
        "Khi thiếu Content-Security-Policy (CSP) hoặc CSP quá lỏng, trình "
        "duyệt sẽ chạy bất kỳ script/style/resource nào được nhúng vào "
        "trang - kể cả script do kẻ tấn công chèn qua XSS - nên các lỗ hổng "
        "client-side gây hậu quả nặng hơn nhiều: đánh cắp cookie/session, "
        "keylogging, chuyển hướng độc hại, và dễ bị clickjacking nếu thiếu "
        "chỉ thị frame-ancestors.\n\n"
        "Khắc phục: cấu hình header Content-Security-Policy giới hạn "
        "default-src, script-src, style-src, frame-ancestors chỉ tới các "
        "nguồn tin cậy, tránh unsafe-inline/unsafe-eval, và bật chế độ "
        "report-only trước khi enforce để kiểm tra tác động."
    ),
    ("jwt", "json web token"): (
        "JWT (JSON Web Token) là một chuỗi mã hoá Base64 gồm 3 phần "
        "(header.payload.signature) dùng để truyền thông tin xác thực/uỷ "
        "quyền giữa các bên một cách tự chứa (self-contained) - server "
        "không cần tra cứu session trong database, chỉ cần xác minh chữ ký.\n\n"
        "Cách hoạt động: server ký payload bằng khoá bí mật (HMAC) hoặc "
        "khoá riêng (RS256/ES256); client gửi kèm token này trong header "
        "Authorization ở mỗi request; server xác minh chữ ký và hạn dùng "
        "(exp) trước khi tin payload.\n\n"
        "Lưu ý bảo mật: payload chỉ được mã hoá Base64 chứ không mã hoá mật "
        "- không đặt dữ liệu nhạy cảm vào đó; luôn đặt thời hạn ngắn (exp) "
        "và dùng refresh token riêng; không bao giờ chấp nhận thuật toán "
        "\"none\"; xác thực đúng thuật toán ký được cấu hình để tránh tấn "
        "công algorithm confusion."
    ),
}

_DEFINITIONS_EN: Final[dict[tuple[str, ...], str]] = {
    ("cvss",): (
        "CVSS (Common Vulnerability Scoring System) is an open standard for "
        "rating vulnerability severity from 0.0 to 10.0. The base score "
        "describes intrinsic characteristics such as attack vector, required "
        "privileges and impact on confidentiality, integrity and availability. "
        "Severity bands: 0.1-3.9 low, 4.0-6.9 medium, 7.0-8.9 high, 9.0-10.0 "
        "critical."
    ),
    ("ssrf", "server-side request forgery"): (
        "SSRF (Server-Side Request Forgery) is a flaw where an attacker makes a "
        "server issue HTTP requests to a target of the attacker's choosing - "
        "typically internal addresses the attacker cannot reach directly, such "
        "as 127.0.0.1 or a cloud metadata endpoint. Defences: allow only "
        "http/https, resolve the hostname and reject private, loopback, "
        "link-local and metadata addresses, re-validate after every redirect, "
        "and cap timeouts and response size."
    ),
    ("phishing",): (
        "Phishing is social engineering that impersonates a trusted party to "
        "get a victim to reveal credentials or run something. Defences that "
        "actually work: phishing-resistant MFA, verifying the sending domain "
        "rather than the display name, and never authenticating through a link "
        "received in a message."
    ),
    ("xss", "cross-site scripting"): (
        "XSS (Cross-Site Scripting) is the injection of attacker-controlled "
        "script into a page another user views. Defences: contextual output "
        "encoding, treating all user input as untrusted when rendering, a "
        "restrictive Content-Security-Policy, and avoiding unsanitised "
        "innerHTML assignments."
    ),
    ("mfa", "multi-factor", "2fa"): (
        "Multi-factor authentication requires more than one kind of evidence to "
        "sign in. Not all factors are equal: hardware security keys and "
        "passkeys resist phishing, push notifications are vulnerable to "
        "fatigue attacks, and SMS codes are vulnerable to SIM swapping."
    ),
    ("zero trust", "zero-trust"): (
        "Zero Trust is an architecture that stops treating network location as "
        "authorisation. Every request is authenticated and authorised on its "
        "own merits, access is least-privilege and time-bounded, and the "
        "assumption is that the network is already compromised."
    ),
    ("sql injection", "sqli", "sql-injection"): (
        "SQL Injection is a flaw where unsanitised user input is concatenated "
        "directly into a SQL statement, letting an attacker alter the query's "
        "logic to read, modify or delete data outside the intended scope, or "
        "bypass authentication entirely. Defences: always use parameterised "
        "queries/prepared statements, never build SQL by string concatenation, "
        "use a safe ORM, apply least-privilege to the database account, and "
        "validate input as a defence-in-depth layer."
    ),
    ("command injection", "os command injection"): (
        "Command Injection is a flaw where unsanitised user input reaches an "
        "OS shell command, letting an attacker run arbitrary commands on the "
        "server. Defences: avoid invoking a shell with user input, call "
        "processes with an argument list (not a shell string), and strictly "
        "whitelist allowed input values."
    ),
    ("csrf", "cross-site request forgery"): (
        "CSRF (Cross-Site Request Forgery) tricks a victim's already "
        "authenticated browser into submitting an unwanted request. "
        "Defences: session-bound CSRF tokens, the SameSite cookie attribute, "
        "and re-authentication for sensitive actions."
    ),
    ("ransomware",): (
        "On detecting ransomware: isolate the infected host from the network "
        "immediately (without powering it off if evidence must be preserved), "
        "scope the blast radius via Assets Inventory and Attack Graph, open "
        "an Incident under Incidents & Tasks, do not pay the ransom, engage "
        "your incident response process, and restore from a verified clean "
        "backup only after confirming the environment is clean."
    ),
    ("mitre att&ck", "mitre attack", "att&ck"): (
        "MITRE ATT&CK is a public knowledge base of adversary tactics and "
        "techniques observed in real-world attacks, organised by attack "
        "lifecycle stage. This platform's MITRE Matrix maps Incidents and "
        "IOCs to their corresponding ATT&CK techniques."
    ),
    ("csp", "content security policy", "content-security-policy"): (
        "Without a Content-Security-Policy (CSP), or with one that is too "
        "permissive, the browser will run any script/style/resource embedded "
        "in the page - including script an attacker injected via XSS - which "
        "makes client-side flaws far more damaging: cookie/session theft, "
        "keylogging, malicious redirects, and clickjacking if frame-ancestors "
        "is missing.\n\n"
        "Fix: configure the Content-Security-Policy header to restrict "
        "default-src, script-src, style-src and frame-ancestors to trusted "
        "sources only, avoid unsafe-inline/unsafe-eval, and roll it out in "
        "report-only mode first to verify impact before enforcing."
    ),
    ("jwt", "json web token"): (
        "A JWT (JSON Web Token) is a Base64-encoded string with 3 parts "
        "(header.payload.signature) used to pass authentication/authorization "
        "claims between parties in a self-contained way - the server doesn't "
        "need to look up a session in a database, only verify the signature.\n\n"
        "How it works: the server signs the payload with a secret (HMAC) or "
        "private key (RS256/ES256); the client sends the token back in the "
        "Authorization header on every request; the server verifies the "
        "signature and expiry (exp) before trusting the payload.\n\n"
        "Security notes: the payload is only Base64-encoded, not encrypted - "
        "never put sensitive data in it; always set a short expiry (exp) and "
        "use a separate refresh token; never accept the \"none\" algorithm; "
        "validate the expected signing algorithm to avoid algorithm-confusion "
        "attacks."
    ),
}


class LocalKnowledgeProvider(BaseLLMProvider):
    """Rule-based knowledge base. Always available, never claims to be a model."""

    name = PROVIDER_NAME

    @property
    def is_configured(self) -> bool:
        # No external dependency, so it is always ready. This is what makes an
        # honest fallback possible when nothing else is configured.
        return True

    async def generate(
        self,
        messages: Sequence[LLMMessage],
        *,
        system_prompt: str,
    ) -> LLMResult:
        question = messages[-1].content if messages else ""
        answer, matched = self._answer(question)
        return LLMResult(
            content=answer,
            provider=self.name,
            model=None,
            metadata={"source": "local_knowledge", "matched": matched},
        )

    def _answer(self, question: str) -> tuple[str, bool]:
        english = wants_english(question)
        intent = classify(question)
        if intent is Intent.GREETING:
            return (_GREETING_ANSWER_EN if english else _GREETING_ANSWER_VI), True
        if intent is Intent.PASSWORD_QUESTION:
            return (_PASSWORD_ANSWER_EN if english else _PASSWORD_ANSWER_VI), True
        if intent is Intent.URL_QUESTION:
            return (_URL_ANSWER_EN if english else _URL_ANSWER_VI), True
        if intent is Intent.CVE_QUESTION:
            return (_CVE_ANSWER_EN if english else _CVE_ANSWER_VI), True

        definition = self._lookup_definition(question, english=english)
        if definition is not None:
            return definition, True

        return (_UNKNOWN_ANSWER_EN if english else _UNKNOWN_ANSWER_VI), False

    @staticmethod
    def _lookup_definition(question: str, *, english: bool) -> Optional[str]:
        text = (question or "").lower()
        definitions = _DEFINITIONS_EN if english else _DEFINITIONS_VI
        for keys, answer in definitions.items():
            if any(key in text for key in keys):
                return answer
        return None
