import os
import sys
from typing import Literal

def init_windows_cuda_path(phase: Literal["pre", "post"]):
    """
    Xử lý thứ tự tìm kiếm DLL CUDA trên Windows để tránh WinError 127/4551.
    - phase='pre': Chạy TRƯỚC khi import bất kỳ thư viện CUDA nào (torch, paddle).
    - phase='post': Chạy SAU khi import paddle nhưng TRƯỚC khi dùng PaddleOCR.
    """
    if sys.platform != "win32":
        return

    root = sys.prefix
    sp = os.path.join(root, "Lib", "site-packages")
    
    # Thư mục chứa DLL của torch
    torch_lib = os.path.join(sp, "torch", "lib")
    
    # Thư mục chứa DLL của nvidia (cài qua pip)
    nvidia_bins = [
        os.path.join(sp, "nvidia", "cudnn", "bin"),
        os.path.join(sp, "nvidia", "cublas", "bin"),
        os.path.join(sp, "nvidia", "cuda_runtime", "bin"),
        os.path.join(sp, "nvidia", "cusolver", "bin"),
        os.path.join(sp, "nvidia", "cusparse", "bin"),
        os.path.join(sp, "nvidia", "cufft", "bin"),
        os.path.join(sp, "nvidia", "curand", "bin"),
        os.path.join(sp, "nvidia", "nvjitlink", "bin"),
        # Bổ sung cu11 cho Paddle 2.6.2
        os.path.join(sp, "nvidia", "cudnn_cu11", "bin"),
        os.path.join(sp, "nvidia", "cublas_cu11", "bin"),
        os.path.join(sp, "nvidia", "cuda_nvrtc_cu11", "bin"),
    ]

    add_dll = getattr(os, "add_dll_directory", None)
    curr_path = os.environ.get("PATH", "")

    def register_paths(paths):
        nonlocal curr_path
        for p in paths:
            if os.path.isdir(p):
                # Prepend to PATH
                curr_path = p + os.pathsep + curr_path
                if callable(add_dll):
                    try:
                        add_dll(p)
                    except OSError:
                        pass
        os.environ["PATH"] = curr_path

    if phase == "pre":
        # Ưu tiên torch lib trước để YOLO ổn định
        # ĐỒNG THỜI thêm nvidia bins luôn để Paddle có thể load được ngay khi import
        to_add = []
        if os.path.isdir(torch_lib):
            to_add.append(torch_lib)
        to_add.extend(nvidia_bins)
        register_paths(to_add)
    elif phase == "post":
        # Phase này có thể giữ nguyên hoặc để trống nếu đã add ở pre
        pass

def check_torch_import():
    """Kiểm tra xem torch có bị chặn bởi App Control không."""
    try:
        import torch
        return True, torch.__version__
    except OSError as e:
        if "4551" in str(e):
            return False, "WinError 4551: Application Control policy blocked torch_python.dll"
        return False, str(e)
    except ImportError as e:
        return False, str(e)
