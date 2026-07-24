"""Swagger UI med lokale assets."""

from fastapi.responses import HTMLResponse


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
        <link rel=\"stylesheet\" href=\"/static/swagger-ui/swagger-ui.css\">
        <link rel=\"icon\" href=\"https://fastapi.tiangolo.com/img/favicon.png\">
      </head>
      <body>
        <div id=\"swagger-ui\"></div>
        <script src=\"/static/swagger-ui/swagger-ui-bundle.js\"></script>
        <script src=\"/static/swagger-ui/swagger-ui-standalone-preset.js\"></script>
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
