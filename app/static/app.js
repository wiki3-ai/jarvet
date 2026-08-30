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

const missionOpeners = {
  "Help me get started finding an education or career path.": {
    message: "Let's find your fastest path. First, do you currently have VA education benefits, such as the GI Bill or VR&E, that you may be eligible to use?",
    suggestions: [
      "Yes, I have GI Bill benefits",
      "I have a disability rating / VR&E",
      "I thought my GI Bill was gone",
      "Not sure what I have",
    ],
  },
  "Help me understand how I can get paid to go to school.": {
    message: "Here are the main ways school may be funded:\n\n• Post-9/11 GI Bill can pay tuition directly to the school and may include a monthly housing allowance and book stipend.\n• Yellow Ribbon can help with tuition above the GI Bill cap at participating schools.\n• VR&E may fund training and provide a subsistence allowance for eligible Veterans with a service-connected disability.\n• If your GI Bill eligibility period ended, there may be circumstances where you can request an extension. Eligibility depends on your situation, so we'll verify the official path before you act.",
    suggestions: [
      "How do I request an extension?",
      "Do I qualify for VR&E?",
      "I'm out of GI Bill months",
      "Help me understand FAFSA",
    ],
  },
  "I want to earn a paycheck while I train.": {
    message: "GI Bill On-the-Job Training and apprenticeships let you work in a real paid job while learning the role. Your employer pays wages, which generally increase as your skills progress, and eligible Veterans may also receive a monthly GI Bill payment that steps down as wages rise.\n\nTell me a location and the kind of work you want, and I'll look for relevant approved opportunities.",
    suggestions: [
      "On-the-job training in Texas",
      "Apprenticeships nationwide",
      "How much would I actually get paid?",
      "I want A+ certification",
    ],
  },
  "Help me figure out what to study.": {
    message: "We can work backward from a career goal, compare occupations using O*NET evidence, and then find matching degree or certificate programs by location. You do not need to know the school first.\n\nChoose an example below, or tell me where you live and what kind of work interests you.",
    suggestions: [
      "Marketing programs in California",
      "Nursing programs in Texas",
      "Welding certificates near me",
      "Help me explore careers first",
    ],
  },
  "I want an A+ computer technician certification.": {
    message: "CompTIA A+ can be a direct route into entry-level IT support work. GI Bill or VR&E may fund approved training, some employers offer IT support apprenticeships or OJT, and eligible licensing or certification test fees may be reimbursable separately from tuition. WIOA may also fund short credentials for eligible job seekers.\n\nTell me your location and we'll find the most relevant route.",
    suggestions: [
      "Find A+ training programs near me",
      "Find an IT apprenticeship instead",
      "I don't have GI Bill benefits left",
    ],
  },
  "Help me understand education benefits for my family.": {
    message: "Several programs may support a spouse or child:\n\n• Transfer of Post-9/11 GI Bill benefits generally must be requested while you are still serving and may carry a service obligation.\n• The Fry Scholarship may support eligible children or surviving spouses of a service member who died in the line of duty.\n• Chapter 35 may support eligible dependents of a Veteran who is permanently and totally disabled due to service, or who died from a service-connected cause.\n• Some states offer dependent tuition waivers with their own residency and eligibility rules.",
    suggestions: [
      "How do I transfer my GI Bill?",
      "Do I qualify for Chapter 35?",
      "Find state tuition waivers",
      "Tell me about the Fry Scholarship",
    ],
  },
};

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

function begin(options = {}) {
  welcome.hidden = true;
  chat.hidden = false;
  messages = [];
  profile = {};
  selectedOccupation = null;
  messagesElement.replaceChildren();
  renderProfile();
  addMessage("assistant", options.message || "What do you need help with today? Choose a starting point or describe your situation in your own words.");
  if (options.message) {
    messages.push({ role: "assistant", content: options.message });
  } else {
    renderStartingPoints();
  }
  renderSuggestions((options.suggestions || []).map(label => ({ label, value: label })));
  input.focus();
}

function beginWithMission(content) {
  const opener = missionOpeners[content];
  if (!opener) {
    begin();
    submitMessage(content);
    return;
  }
  begin(opener);
}

welcomeForm.addEventListener("submit", event => {
  event.preventDefault();
  const content = welcomeInput.value.trim();
  if (content) {
    begin();
    submitMessage(content);
  }
});
for (const mission of document.querySelectorAll(".mission")) {
  mission.addEventListener("click", () => beginWithMission(mission.dataset.message));
}
document.querySelector("#reset").addEventListener("click", () => begin());
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