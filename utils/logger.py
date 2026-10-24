import sys
import time
import traceback
from datetime import datetime
from typing import Optional

# ANSI Color codes for clean and prominent terminal display
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"

def _get_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _safe_print(text: str):
    """Đảm bảo in an toàn ra terminal không bị crash mã hóa trên mọi môi trường."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            print(text.encode("utf-8", errors="replace").decode("ascii", errors="replace"), flush=True)
        except Exception:
            pass

def log_banner(title: str):
    _safe_print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 85}{Colors.RESET}")
    _safe_print(f"{Colors.BOLD}{Colors.CYAN}[HỆ THỐNG MULTI-AGENT VQA] {title.upper()}{Colors.RESET}")
    _safe_print(f"{Colors.DIM}Thời gian: {_get_time()}{Colors.RESET}")
    _safe_print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 85}{Colors.RESET}")

def log_separator():
    _safe_print(f"{Colors.DIM}{'-' * 85}{Colors.RESET}")

def log_info(msg: str):
    _safe_print(f"{Colors.DIM}[{_get_time()}]{Colors.RESET} {Colors.BLUE}[INFO]{Colors.RESET} {msg}")

def log_agent_start(agent_name: str, task_desc: str):
    _safe_print(
        f"{Colors.DIM}[{_get_time()}]{Colors.RESET} "
        f"{Colors.BOLD}{Colors.CYAN}[AGENT KÍCH HOẠT]{Colors.RESET} "
        f"{Colors.BOLD}{agent_name}{Colors.RESET} -> {task_desc}"
    )

def log_agent_success(agent_name: str, duration: float, summary: str = ""):
    summary_str = f" | {summary}" if summary else ""
    _safe_print(
        f"{Colors.DIM}[{_get_time()}]{Colors.RESET} "
        f"{Colors.GREEN}[AGENT HOÀN THÀNH]{Colors.RESET} "
        f"{Colors.BOLD}{agent_name}{Colors.RESET} "
        f"{Colors.YELLOW}({duration:.2f}s){Colors.RESET}{summary_str}"
    )

def log_api_call(provider: str, model: str, has_image: bool = False, prompt_len: int = 0):
    img_tag = f"{Colors.MAGENTA}[CÓ ẢNH]{Colors.RESET}" if has_image else "[CHỈ CHỮ]"
    _safe_print(
        f"{Colors.DIM}[{_get_time()}]{Colors.RESET} "
        f"{Colors.YELLOW}[API CALL]{Colors.RESET} "
        f"Provider: {Colors.BOLD}{provider.upper()}{Colors.RESET} | Model: {Colors.BOLD}{model}{Colors.RESET} {img_tag} | Prompt: {prompt_len} ký tự"
    )

def log_api_success(provider: str, model: str, duration: float, response_len: int = 0):
    _safe_print(
        f"{Colors.DIM}[{_get_time()}]{Colors.RESET} "
        f"{Colors.GREEN}[API SUCCESS]{Colors.RESET} "
        f"{provider.upper()} ({model}) hoàn thành trong {Colors.YELLOW}{duration:.2f}s{Colors.RESET} | Phản hồi: {response_len} ký tự"
    )

def log_error(caller_name: str, error: Exception, details: Optional[str] = None):
    """In chi tiết lỗi nổi bật với khung viền đỏ, tên module và Full Stack Trace."""
    err_type = type(error).__name__
    err_msg = str(error)
    tb_str = traceback.format_exc()

    _safe_print(f"\n{Colors.BG_RED}{Colors.WHITE}{Colors.BOLD} [LỖI HỆ THỐNG / RUNTIME ERROR] {Colors.RESET}")
    _safe_print(f"{Colors.RED}{Colors.BOLD}Vị trí phát sinh: {caller_name}{Colors.RESET}")
    _safe_print(f"{Colors.RED}Loại lỗi         : {err_type}{Colors.RESET}")
    _safe_print(f"{Colors.RED}Thông báo lỗi   : {err_msg}{Colors.RESET}")
    if details:
        _safe_print(f"{Colors.YELLOW}Thông tin bổ sung: {details}{Colors.RESET}")
    
    _safe_print(f"{Colors.DIM}Chi tiết Stack Trace:{Colors.RESET}")
    _safe_print(f"{Colors.RED}{tb_str}{Colors.RESET}")
    _safe_print(f"{Colors.RED}{'=' * 85}{Colors.RESET}\n")

def log_warning(msg: str):
    _safe_print(f"{Colors.DIM}[{_get_time()}]{Colors.RESET} {Colors.YELLOW}[CẢNH BÁO]{Colors.RESET} {msg}")
