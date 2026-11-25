// InventAI/o — CloudFront Function del comportamiento por defecto (la web en S3). La aplicación es una SPA: una ruta
// sin extensión (/recomendaciones, /chat) es una pantalla de React, así que se pide index.html. Los archivos con
// extensión (/assets/index-abc.js) van tal cual. /api/* no pasa por aquí: tiene su propio comportamiento.
// No se usan las respuestas de error personalizadas de CloudFront: valen para toda la distribución y convertirían
// un 404 del api en index.html.
function handler(event) {
  var request = event.request;
  var ultimo = request.uri.split("/").pop();
  if (ultimo.indexOf(".") === -1) {
    request.uri = "/index.html";
  }
  return request;
}
