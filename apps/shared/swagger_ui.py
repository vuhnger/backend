"""Swagger UI med lokale assets (ingen tredjeparts-CDN)."""

import html as html_lib
import json

from fastapi.responses import HTMLResponse

# Swagger UI kjører en inline init-script og injiserer inline-stiler, så selve
# docs-siden trenger en løsere CSP enn resten av API-et. Vi scoper
# 'unsafe-inline' hit (kun på docs-responsen) i stedet for globalt, slik at det
# strenge policyet i security_headers.py fortsatt gjelder for alt annet.
_SWAGGER_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'"
)


def render_swagger_ui_html(
    openapi_url: str, title: str, oauth2_redirect_url: str
) -> HTMLResponse:
    """Render Swagger UI fra lokale /static-assets.

    Verdiene interpoleres inn i HTML/inline-JS, så de escapes: html.escape for
    tittelen og json.dumps for verdier som havner i script-konteksten.
    """
    safe_title = html_lib.escape(title)
    js_openapi_url = json.dumps(openapi_url)
    js_oauth2_redirect_url = json.dumps(oauth2_redirect_url)

    body = f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title} - Swagger UI</title>
    <link rel="stylesheet" href="/static/swagger-ui/swagger-ui.css">
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="/static/swagger-ui/swagger-ui-bundle.js"></script>
    <script src="/static/swagger-ui/swagger-ui-standalone-preset.js"></script>
    <script>
      const ui = SwaggerUIBundle({{
        url: {js_openapi_url},
        dom_id: '#swagger-ui',
        layout: 'BaseLayout',
        deepLinking: true,
        showExtensions: true,
        showCommonExtensions: true,
        oauth2RedirectUrl: window.location.origin + {js_oauth2_redirect_url},
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
      }});
    </script>
  </body>
</html>"""

    return HTMLResponse(body, headers={"Content-Security-Policy": _SWAGGER_CSP})
