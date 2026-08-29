const welcome = document.querySelector("#welcome");
const chat = document.querySelector("#chat");
const messagesElement = document.querySelector("#messages");
const form = document.querySelector("#form");
const input = document.querySelector("#input");
const send = document.querySelector("#send");
let messages = [];

function addMessage(role, content, extraClass = "") {
  const element = document.createElement("div");
  element.className = `message ${role} ${extraClass}`;
  element.textContent = content;
  messagesElement.appendChild(element);
  messagesElement.scrollTop = messagesElement.scrollHeight;
  return element;
}

function begin() {
  welcome.hidden = true;
  chat.hidden = false;
  messages = [];
  messagesElement.replaceChildren();
  addMessage("assistant", "What kind of future are you considering? Tell me about work you enjoy, subjects that hold your attention, or a role you are curious about.");
  input.focus();
}

document.querySelector("#start").addEventListener("click", begin);
document.querySelector("#reset").addEventListener("click", begin);
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
});
input.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  const content = input.value.trim();
  if (!content) return;
  messages.push({ role: "user", content });
  addMessage("user", content);
  input.value = "";
  input.style.height = "auto";
  send.disabled = true;
  const thinking = addMessage("assistant", "Looking through O*NET…", "thinking");
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Request failed");
    thinking.remove();
    messages.push({ role: "assistant", content: body.message });
    addMessage("assistant", body.message);
  } catch (error) {
    thinking.textContent = `I couldn't reach the guide: ${error.message}`;
    thinking.classList.remove("thinking");
  } finally {
    send.disabled = false;
    input.focus();
  }
});