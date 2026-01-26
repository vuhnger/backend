"""Swagger UI med Subresource Integrity (SRI)."""

from fastapi.responses import HTMLResponse

SWAGGER_UI_CSS_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css"
SWAGGER_UI_BUNDLE_URL = (
    "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"
)
SWAGGER_UI_STANDALONE_URL = (
    "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-standalone-preset.js"
)

SWAGGER_UI_CSS_INTEGRITY = (
    "sha384-ZJ2d83jl4Lvr6GKYzXpvQUmu+8us6T5frIryNHoLuypLK61jUnnCWZWyyrnifLda"
)
SWAGGER_UI_BUNDLE_INTEGRITY = (
    "sha384-yrdF3mlUytUBwQyEVFAdwuUKEC9Qqrf+IUCgFgho4O5O6irf77pMjv36FN4eTpQD"
)
SWAGGER_UI_STANDALONE_INTEGRITY = (
    "sha384-azzkurII4f+bjmZvm3hWhj7JezshyXtwobwneRyWCCIksK61Xi0Ry3xA2am9/TWp"
)


def render_swagger_ui_html(
    openapi_url: str, title: str, oauth2_redirect_url: str
) -> HTMLResponse:
    html = f"""
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
        <title>{title} - Swagger UI</title>
        <link rel=\"stylesheet\" href=\"{SWAGGER_UI_CSS_URL}\" integrity=\"{SWAGGER_UI_CSS_INTEGRITY}\" crossorigin=\"anonymous\">
        <link rel=\"icon\" href=\"https://fastapi.tiangolo.com/img/favicon.png\">
      </head>
      <body>
        <div id=\"swagger-ui\"></div>
        <script src=\"{SWAGGER_UI_BUNDLE_URL}\" integrity=\"{SWAGGER_UI_BUNDLE_INTEGRITY}\" crossorigin=\"anonymous\"></script>
        <script src=\"{SWAGGER_UI_STANDALONE_URL}\" integrity=\"{SWAGGER_UI_STANDALONE_INTEGRITY}\" crossorigin=\"anonymous\"></script>
        <script>
          const ui = SwaggerUIBundle({{
            url: '{openapi_url}',
            dom_id: '#swagger-ui',
            layout: 'BaseLayout',
            deepLinking: true,
            showExtensions: true,
            showCommonExtensions: true,
            oauth2RedirectUrl: window.location.origin + '{oauth2_redirect_url}',
            presets: [
              SwaggerUIBundle.presets.apis,
              SwaggerUIStandalonePreset
            ],
          }});
        </script>
      </body>
    </html>
    """

    return HTMLResponse(html)
