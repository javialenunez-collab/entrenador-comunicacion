let categoriaActual = "";
let consignaActual = "";
let modoActual = "texto";
let reconociendo = null;

const elConsignaBox = document.getElementById("consigna-box");
const elConsignaTexto = document.getElementById("consigna-texto");
const elRespuestaBox = document.getElementById("respuesta-box");
const elTextoRespuesta = document.getElementById("texto-respuesta");
const elBtnMic = document.getElementById("btn-mic");
const elEstadoMic = document.getElementById("estado-mic");
const elBtnEnviar = document.getElementById("btn-enviar");
const elCargando = document.getElementById("cargando");
const elFeedbackBox = document.getElementById("feedback-box");
const elHistorial = document.getElementById("historial");
const elRachaNumero = document.getElementById("racha-numero");

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => pedirConsigna(chip.dataset.categoria));
});

elBtnEnviar.addEventListener("click", enviarRespuesta);
elBtnMic.addEventListener("click", toggleMicrofono);

async function pedirConsigna(categoria) {
  const resp = await fetch(`/api/consigna?categoria=${encodeURIComponent(categoria)}`);
  const data = await resp.json();
  categoriaActual = data.categoria;
  consignaActual = data.consigna;

  elConsignaTexto.textContent = data.consigna;
  elConsignaBox.hidden = false;
  elRespuestaBox.hidden = false;
  elFeedbackBox.hidden = true;
  elFeedbackBox.innerHTML = "";
  elTextoRespuesta.value = "";
  modoActual = "texto";
}

function toggleMicrofono() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    elEstadoMic.textContent = "Tu navegador no soporta dictado por voz. Usá Chrome.";
    return;
  }

  if (reconociendo) {
    reconociendo.stop();
    return;
  }

  reconociendo = new SpeechRecognition();
  reconociendo.lang = "es-ES";
  reconociendo.continuous = true;
  reconociendo.interimResults = true;

  const textoBase = elTextoRespuesta.value ? elTextoRespuesta.value + " " : "";

  reconociendo.onstart = () => {
    elBtnMic.classList.add("grabando");
    elEstadoMic.textContent = "Escuchando...";
    modoActual = "voz";
  };

  reconociendo.onresult = (event) => {
    let textoFinal = "";
    let textoParcial = "";
    for (let i = 0; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        textoFinal += event.results[i][0].transcript;
      } else {
        textoParcial += event.results[i][0].transcript;
      }
    }
    elTextoRespuesta.value = textoBase + textoFinal + textoParcial;
  };

  reconociendo.onerror = (event) => {
    elEstadoMic.textContent = "Hubo un error con el micrófono (" + event.error + ").";
  };

  reconociendo.onend = () => {
    elBtnMic.classList.remove("grabando");
    elEstadoMic.textContent = "";
    reconociendo = null;
  };

  reconociendo.start();
}

async function enviarRespuesta() {
  const texto = elTextoRespuesta.value.trim();
  if (!texto) return;

  elBtnEnviar.disabled = true;
  elCargando.hidden = false;
  elFeedbackBox.hidden = true;

  try {
    const resp = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        categoria: categoriaActual,
        consigna: consignaActual,
        texto: texto,
        modo: modoActual,
      }),
    });

    const data = await resp.json();

    if (!resp.ok) {
      elFeedbackBox.hidden = false;
      elFeedbackBox.innerHTML = `<div class="feedback-bloque">⚠️ ${data.error}</div>`;
      return;
    }

    mostrarFeedback(data.feedback);
    elRachaNumero.textContent = data.racha;
    cargarHistorial();
  } finally {
    elBtnEnviar.disabled = false;
    elCargando.hidden = true;
  }
}

function mostrarFeedback(fb) {
  elFeedbackBox.hidden = false;
  let html = "";

  if (fb.resumen_breve) {
    html += `<div class="feedback-bloque"><h3>Resumen</h3><p>${escapeHtml(fb.resumen_breve)}</p></div>`;
  }

  if (fb.muletillas && fb.muletillas.length) {
    html += `<div class="feedback-bloque"><h3>Muletillas</h3><p>${fb.muletillas.map(escapeHtml).join(", ")}</p></div>`;
  }

  if (fb.palabras_repetidas && fb.palabras_repetidas.length) {
    html += `<div class="feedback-bloque"><h3>Palabras repetidas</h3><p>${fb.palabras_repetidas.map(escapeHtml).join(", ")}</p></div>`;
  }

  if (fb.reescritura_sugerida) {
    html += `<div class="feedback-bloque"><h3>Una forma más clara de decirlo</h3><p>${escapeHtml(fb.reescritura_sugerida)}</p></div>`;
  }

  if (fb.palabras_nuevas && fb.palabras_nuevas.length) {
    const items = fb.palabras_nuevas
      .map(
        (p) =>
          `<div class="palabra-nueva"><span class="en-vez-de">${escapeHtml(p.en_vez_de)}</span> → <span class="podrias-decir">${escapeHtml(p.podrias_decir)}</span><br><small>${escapeHtml(p.por_que || "")}</small></div>`
      )
      .join("");
    html += `<div class="feedback-bloque"><h3>Palabras para sumar</h3>${items}</div>`;
  }

  if (fb.consejo_practica) {
    html += `<div class="feedback-bloque"><h3>Para la próxima</h3><p>${escapeHtml(fb.consejo_practica)}</p></div>`;
  }

  elFeedbackBox.innerHTML = html;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function cargarHistorial() {
  const resp = await fetch("/api/historial");
  const items = await resp.json();

  elHistorial.innerHTML = items
    .map(
      (item) => `
      <div class="historial-item">
        <div class="fecha">${item.fecha} · ${item.categoria}</div>
        <div><strong>${escapeHtml(item.consigna)}</strong></div>
        <div>${escapeHtml(item.feedback.resumen_breve || "")}</div>
      </div>`
    )
    .join("");
}

async function cargarRacha() {
  const resp = await fetch("/api/racha");
  const data = await resp.json();
  elRachaNumero.textContent = data.racha;
}

cargarHistorial();
cargarRacha();
