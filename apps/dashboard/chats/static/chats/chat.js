document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("chat-container");
  if (!container) return;

  const apiUrl    = container.dataset.apiUrl;
  const streamUrl = container.dataset.streamUrl;
  const sessionId = container.dataset.sessionId;
  const form      = document.getElementById("chat-form");
  const messages  = document.getElementById("messages");

  // 1) submit normal (fallback no-stream)
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = form.message.value.trim();
    if (!text) return;
    appendMsg("user", text);
    form.message.value = "";
    stream(text);        // usa SSE
  });

  function appendMsg(role, html) {
    const div = document.createElement("div");
    div.className = "msg "+role;
    div.innerHTML = html;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  function stream(text) {
    // abre SSE
    fetch(streamUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message:text, session_id:sessionId })
    })
    .then(resp => {
      const reader = resp.body.getReader();
      let buffer = "";
      function read() {
        reader.read().then(({done,value})=>{
          if (done) { appendMsg("assistant", buffer); return; }
          buffer += new TextDecoder().decode(value);
          // opcional: pintar tokens en live
          read();
        });
      }
      read();
    });
  }
});
