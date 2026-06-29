"""Production uvicorn entry (Docker entrypoint). Disables WS library ping (app sends 'ka')."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    server_root = Path(__file__).resolve().parent
    os.chdir(server_root)
    sr = str(server_root)
    if sr not in sys.path:
        sys.path.insert(0, sr)

    from app.utils.ai.gpu_bootstrap import reexec_with_cuda_bootstrap_if_needed

    reexec_with_cuda_bootstrap_if_needed()

    import uvicorn

    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '8080'))
    uvicorn.run(
        'app.main:app',
        host=host,
        port=port,
        workers=1,
        ws='wsproto',
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )


if __name__ == '__main__':
    main()
