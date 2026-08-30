const welcome = document.querySelector("#welcome");
const chat = document.querySelector("#chat");
const messagesElement = document.querySelector("#messages");
const form = document.querySelector("#form");
const input = document.querySelector("#input");
const send = document.querySelector("#send");
const profileElement = document.querySelector("#profile");
const profileItems = document.querySelector("#profile-items");
const suggestionsElement = document.querySelector("#suggestions");
const welcomeForm = document.querySelector("#welcome-form");
const welcomeInput = document.querySelector("#welcome-input");
let messages = [];
let profile = {};
let selectedOccupation = null;

const startingPoints = [
  {
    title: "Benefits",
    options: [
      "I was just discharged",
      "Help me use my GI Bill benefits",
      "I used all of my GI Bill benefits. What now?",
      "My benefits expired. What can I do?",
      "I don't qualify for benefits",
    ],
  },
  {
    title: "School and training",
    options: [
      "I can't find a school for the degree I want",
      "I want vocational training",
      "I want on-the-job training",
      "I want to get paid while I train",
    ],
  },
  {
    title: "Career ideas",
    options: [
      "I want an A+ computer technician certificate",
      "I want to be an underwater welder",
    ],
  },
];

function appendLinkedText(element, content, resources) {
  const links = resources.flatMap(resource =>
    (resource.inline_labels || []).map(label => ({
      label,
      url: resource.url,
      priority: resource.kind === "program-details" ? 3
        : resource.kind === "provider-details" ? 2 : 1,
    }))
  ).filter(link => link.label && link.url)
    .sort((first, second) => second.label.length - first.label.length
      || second.priority - first.priority);
  if (!links.length) {
    element.textContent = content;
    return;
  }

  const escaped = links.map(link => link.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const byLabel = new Map();
  for (const link of links) {
    if (!byLabel.has(link.label.toLowerCase())) {
      byLabel.set(link.label.toLowerCase(), link);
    }
  }
  for (const part of content.split(pattern)) {
    const link = byLabel.get(part.toLowerCase());
    if (!link) {
      element.append(document.createTextNode(part));
      continue;
    }
    const anchor = document.createElement("a");
    anchor.href = link.url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.textContent = part;
    element.append(anchor);
  }
}

function addMessage(role, content, extraClass = "", resources = []) {
  const element = document.createElement("div");
  element.className = `message ${role} ${extraClass}`;
  appendLinkedText(element, content, resources);
  messagesElement.appendChild(element);
  messagesElement.scrollTop = messagesElement.scrollHeight;
  return element;
}

function renderSuggestions(suggestions = []) {
  suggestionsElement.replaceChildren();
  for (const suggestion of suggestions) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = suggestion.label;
    button.addEventListener("click", () => submitMessage(suggestion.value));
    suggestionsElement.appendChild(button);
  }
}

function renderStartingPoints() {
  const panel = document.createElement("section");
  panel.className = "starting-points";
  for (const group of startingPoints) {
    const section = document.createElement("div");
    section.className = "starting-group";
    const title = document.createElement("h2");
    title.textContent = group.title;
    section.appendChild(title);
    for (const option of group.options) {
      const button = document.createElement("button");
      button.type = "button";
      button.innerHTML = `<span>${option}</span><span aria-hidden="true">→</span>`;
      button.addEventListener("click", () => submitMessage(option));
      section.appendChild(button);
    }
    panel.appendChild(section);
  }
  messagesElement.appendChild(panel);
}

function renderResources(resources = []) {
  if (!resources.length) return;
  const list = document.createElement("div");
  list.className = "resource-list";
  for (const resource of resources) {
    const link = document.createElement("a");
    link.href = resource.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.innerHTML = `<span>${resource.label}</span><span aria-hidden="true">↗</span>`;
    list.appendChild(link);
  }
  messagesElement.appendChild(list);
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

function renderProfile() {
  profileItems.replaceChildren();
  if (selectedOccupation) {
    const occupation = document.createElement("button");
    occupation.type = "button";
    occupation.className = "profile-item";
    occupation.title = `Stop focusing on ${selectedOccupation.title}`;
    occupation.textContent = selectedOccupation.title;
    occupation.addEventListener("click", () => {
      selectedOccupation = null;
      renderProfile();
    });
    profileItems.appendChild(occupation);
  }
  for (const [field, values] of Object.entries(profile)) {
    for (const value of values) {
      if (selectedOccupation && value.toLowerCase() === selectedOccupation.title.toLowerCase()) {
        continue;
      }
      const item = document.createElement("button");
      item.type = "button";
      item.className = "profile-item";
      item.title = `Remove ${value}`;
      item.textContent = value;
      item.addEventListener("click", () => {
        profile[field] = profile[field].filter(entry => entry !== value);
        renderProfile();
      });
      profileItems.appendChild(item);
    }
  }
  profileElement.hidden = profileItems.childElementCount === 0;
}

function begin() {
  welcome.hidden = true;
  chat.hidden = false;
  messages = [];
  profile = {};
  selectedOccupation = null;
  messagesElement.replaceChildren();
  renderProfile();
  addMessage("assistant", "What do you need help with today? Choose a starting point or describe your situation in your own words.");
  renderStartingPoints();
  renderSuggestions();
  input.focus();
}

function beginWithMessage(content) {
  begin();
  submitMessage(content);
}

welcomeForm.addEventListener("submit", event => {
  event.preventDefault();
  const content = welcomeInput.value.trim();
  if (content) beginWithMessage(content);
});
for (const mission of document.querySelectorAll(".mission")) {
  mission.addEventListener("click", () => beginWithMessage(mission.dataset.message));
}
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

async function submitMessage(rawContent) {
  const content = rawContent.trim();
  if (!content) return;
  document.querySelector(".starting-points")?.remove();
  renderSuggestions();
  messages.push({ role: "user", content });
  addMessage("user", content);
  input.value = "";
  input.style.height = "auto";
  send.disabled = true;
  const thinking = addMessage("assistant", "Finding the right path…", "thinking");
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, profile, selected_occupation: selectedOccupation }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Request failed");
    thinking.remove();
    messages.push({ role: "assistant", content: body.message });
    addMessage("assistant", body.message, "", body.resources || []);
    renderResources(body.resources);
    profile = body.profile || profile;
    selectedOccupation = body.selected_occupation || selectedOccupation;
    renderProfile();
    renderSuggestions(body.suggestions);
  } catch (error) {
    thinking.textContent = `I couldn't reach the guide: ${error.message}`;
    thinking.classList.remove("thinking");
  } finally {
    send.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  await submitMessage(input.value);
});