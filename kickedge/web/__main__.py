"""Run the KickEdge web service: python -m kickedge.web (PORT/HOST env optional)."""
import os

import uvicorn

uvicorn.run('kickedge.web.app:app', host=os.environ.get('HOST', '127.0.0.1'),
            port=int(os.environ.get('PORT', '8000')), proxy_headers=True)
