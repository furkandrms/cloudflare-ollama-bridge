const chatEl = document.getElementById("chat");
const formEl = document.getElementById("chat-form");
const messageEl = document.getElementById("message");
const sendBtn = document.getElementById("send-btn");
const serverUrlEl = document.getElementById("server-url");
const modelEl = document.getElementById("model");

function addBubble(text, kind) {
  const div = document.createElement("div");
  div.className = `bubble ${kind}`;
  div.textContent = text;
  chatEl.appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
  return div;
}

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = messageEl.value.trim();
  if (!message) return;

  addBubble(message, "user");
  messageEl.value = "";
  sendBtn.disabled = true;

  const botBubble = addBubble("", "bot");

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        server_url: serverUrlEl.value.trim(),
        model: modelEl.value.trim(),
      }),
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let full = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      full += decoder.decode(value, { stream: true });
      botBubble.textContent = full;
      botBubble.scrollIntoView({ behavior: "smooth", block: "end" });
    }
    if (full.startsWith("[error]")) {
      botBubble.className = "bubble error";
    }
  } catch (err) {
    botBubble.className = "bubble error";
    botBubble.textContent = `[error] ${err.message}`;
  } finally {
    sendBtn.disabled = false;
    messageEl.focus();
  }
});

messageEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});
