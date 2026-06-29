"""CUDA/cuDNN library path bootstrap for torch + paddle in one process."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

_CUDA_BOOTSTRAP_DONE = False
_RUNTIME_CUDNN_LINK_DIR: Path | None = None

# Paddle dlopen unversioned .so names; nvidia wheels ship only .so.N
_RUNTIME_CUDA_SYMLINKS: tuple[tuple[str, str, str], ...] = (
    ('libcudnn.so', 'nvidia/cudnn/lib', 'libcudnn.so.9'),
    ('libcublas.so', 'nvidia/cublas/lib', 'libcublas.so.12'),
    ('libcublasLt.so', 'nvidia/cublas/lib', 'libcublasLt.so.12'),
)


def _site_packages() -> str:
    return os.path.join(sys.prefix, 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')


def _existing_dirs(paths: list[str]) -> list[str]:
    return [path for path in paths if os.path.isdir(path)]


def _nvidia_lib_dirs(site_packages: str) -> list[str]:
    names = (
        'cudnn',
        'cublas',
        'cuda_runtime',
        'cusolver',
        'cusparse',
        'cufft',
        'curand',
        'nvjitlink',
        'cuda_nvrtc',
    )
    return _existing_dirs([os.path.join(site_packages, 'nvidia', name, 'lib') for name in names])


def _prepend_env_path(key: str, paths: list[str], *, separator: str) -> None:
    existing = os.environ.get(key, '')
    prefix = separator.join(paths)
    if not prefix:
        return
    os.environ[key] = f'{prefix}{separator}{existing}' if existing else prefix


def _init_linux_cuda_path() -> None:
    """Prefer Paddle's cuDNN 9.5 wheels over torch's bundled cuDNN 9.1."""
    global _CUDA_BOOTSTRAP_DONE
    if _CUDA_BOOTSTRAP_DONE:
        return

    site_packages = _site_packages()
    cudnn_lib = os.path.join(site_packages, 'nvidia', 'cudnn', 'lib')
    torch_lib = os.path.join(site_packages, 'torch', 'lib')

    lib_dirs = _nvidia_lib_dirs(site_packages)
    if os.path.isdir(torch_lib):
        lib_dirs.append(torch_lib)
    _prepend_env_path('LD_LIBRARY_PATH', lib_dirs, separator=':')

    preload_libs = [
        os.path.join(cudnn_lib, 'libcudnn.so.9'),
        os.path.join(cudnn_lib, 'libcudnn_graph.so.9'),
    ]
    preload_libs = [path for path in preload_libs if os.path.isfile(path)]
    if preload_libs:
        _prepend_env_path('LD_PRELOAD', preload_libs, separator=':')

    _CUDA_BOOTSTRAP_DONE = True


def _init_windows_cuda_path(phase: Literal['pre', 'post']) -> None:
    root = sys.prefix
    site_packages = os.path.join(root, 'Lib', 'site-packages')
    torch_lib = os.path.join(site_packages, 'torch', 'lib')
    nvidia_bins = [
        os.path.join(site_packages, 'nvidia', 'cudnn', 'bin'),
        os.path.join(site_packages, 'nvidia', 'cublas', 'bin'),
        os.path.join(site_packages, 'nvidia', 'cuda_runtime', 'bin'),
        os.path.join(site_packages, 'nvidia', 'cusolver', 'bin'),
        os.path.join(site_packages, 'nvidia', 'cusparse', 'bin'),
        os.path.join(site_packages, 'nvidia', 'cufft', 'bin'),
        os.path.join(site_packages, 'nvidia', 'curand', 'bin'),
        os.path.join(site_packages, 'nvidia', 'nvjitlink', 'bin'),
        os.path.join(site_packages, 'nvidia', 'cudnn_cu11', 'bin'),
        os.path.join(site_packages, 'nvidia', 'cublas_cu11', 'bin'),
        os.path.join(site_packages, 'nvidia', 'cuda_nvrtc_cu11', 'bin'),
    ]

    add_dll = getattr(os, 'add_dll_directory', None)
    curr_path = os.environ.get('PATH', '')

    def register_paths(paths: list[str]) -> None:
        nonlocal curr_path
        for path in paths:
            if os.path.isdir(path):
                curr_path = path + os.pathsep + curr_path
                if callable(add_dll):
                    try:
                        add_dll(path)
                    except OSError:
                        pass
        os.environ['PATH'] = curr_path

    if phase == 'pre':
        to_add: list[str] = []
        if os.path.isdir(torch_lib):
            to_add.append(torch_lib)
        to_add.extend(nvidia_bins)
        register_paths(to_add)


def init_cuda_library_path(phase: Literal['pre', 'post'] = 'pre') -> None:
    """
    Align CUDA library resolution before importing torch/paddle.
    - Linux: LD_PRELOAD/LD_LIBRARY_PATH so Paddle cuDNN 9.5 wins over torch cuDNN 9.1.
    - Windows: PATH + add_dll_directory for torch + nvidia pip wheels.
    """
    if sys.platform == 'win32':
        _init_windows_cuda_path(phase)
        return
    if phase == 'pre':
        _init_linux_cuda_path()


# Backward-compatible alias used across the codebase.
init_windows_cuda_path = init_cuda_library_path


def cuda_bootstrap_applied() -> bool:
    return _CUDA_BOOTSTRAP_DONE or sys.platform == 'win32'


def _linux_cudnn_preload_paths() -> list[str]:
    cudnn_lib = os.path.join(_site_packages(), 'nvidia', 'cudnn', 'lib')
    candidates = [
        os.path.join(cudnn_lib, 'libcudnn.so.9'),
        os.path.join(cudnn_lib, 'libcudnn_graph.so.9'),
    ]
    return [path for path in candidates if os.path.isfile(path)]


def _runtime_cuda_link_dir() -> Path | None:
    """Symlink unversioned CUDA libs Paddle expects (libcudnn.so, libcublas.so, …)."""
    global _RUNTIME_CUDNN_LINK_DIR
    if _RUNTIME_CUDNN_LINK_DIR is not None:
        return _RUNTIME_CUDNN_LINK_DIR

    site = Path(_site_packages())
    runtime_dir = Path(__file__).resolve().parents[3] / 'app' / 'runtime-media' / 'cuda-libs'
    runtime_dir.mkdir(parents=True, exist_ok=True)
    linked = False
    for link_name, rel_lib_dir, target_name in _RUNTIME_CUDA_SYMLINKS:
        target = site / rel_lib_dir / target_name
        if not target.is_file():
            continue
        link = runtime_dir / link_name
        if not link.exists():
            link.symlink_to(target)
        linked = True

    if not linked:
        return None

    _RUNTIME_CUDNN_LINK_DIR = runtime_dir
    return runtime_dir


def _runtime_cudnn_link_dir() -> Path | None:
    return _runtime_cuda_link_dir()


def prepare_paddle_subprocess_env() -> dict[str, str]:
    """
    LD_PRELOAD / LD_LIBRARY_PATH for a Paddle-only child process.
    Must be applied to os.environ before multiprocessing spawn (LD_PRELOAD is exec-time).
    """
    site_packages = _site_packages()
    cudnn_lib = os.path.join(site_packages, 'nvidia', 'cudnn', 'lib')
    lib_dirs: list[str] = []
    runtime_dir = _runtime_cudnn_link_dir()
    if runtime_dir is not None:
        lib_dirs.append(str(runtime_dir))
    if os.path.isdir(cudnn_lib):
        lib_dirs.append(cudnn_lib)
    lib_dirs.extend(_nvidia_lib_dirs(site_packages))

    patch: dict[str, str] = {}
    if lib_dirs:
        existing = os.environ.get('LD_LIBRARY_PATH', '')
        prefix = ':'.join(lib_dirs)
        patch['LD_LIBRARY_PATH'] = f'{prefix}:{existing}' if existing else prefix

    preload_libs = _linux_cudnn_preload_paths()
    if preload_libs:
        existing = os.environ.get('LD_PRELOAD', '')
        prefix = ':'.join(preload_libs)
        patch['LD_PRELOAD'] = f'{prefix}:{existing}' if existing else prefix

    return patch


def apply_env_patch(patch: dict[str, str]) -> dict[str, str | None]:
    saved: dict[str, str | None] = {}
    for key, value in patch.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    return saved


def restore_env_patch(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def reexec_with_cuda_bootstrap_if_needed() -> None:
    """
    Linux: LD_PRELOAD chỉ có hiệu lực khi set trước exec().
    Gọi sớm trong run_dev/run_prod trước khi import torch/paddle.
    """
    if sys.platform == 'win32':
        return
    if os.environ.get('_DOCK_CUDA_BOOTSTRAP') == '1':
        init_cuda_library_path('pre')
        return

    preload_libs = _linux_cudnn_preload_paths()
    if not preload_libs:
        return

    env = os.environ.copy()
    existing = env.get('LD_PRELOAD', '')
    prefix = ':'.join(preload_libs)
    env['LD_PRELOAD'] = f'{prefix}:{existing}' if existing else prefix
    env['_DOCK_CUDA_BOOTSTRAP'] = '1'
    os.execve(sys.executable, [sys.executable, *sys.argv], env)


def check_torch_import():
    """Kiểm tra xem torch có bị chặn bởi App Control không."""
    try:
        import torch

        return True, torch.__version__
    except OSError as e:
        if '4551' in str(e):
            return False, 'WinError 4551: Application Control policy blocked torch_python.dll'
        return False, str(e)
    except ImportError as e:
        return False, str(e)
