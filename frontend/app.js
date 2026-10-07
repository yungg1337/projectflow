/* Клиентское приложение ProjectFlow: обращается к REST API через fetch. */
const API = "/api/v1";
const state = { token: localStorage.getItem("pf_token"), user: null, projects: [], users: [] };

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = "Bearer " + state.token;
  const response = await fetch(API + path, {
    method: options.method || "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (response.status === 204) return {};
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Ошибка запроса");
  return data;
}

function showMessage(element, text, ok = false) {
  element.textContent = text;
  element.style.color = ok ? "#2e7d32" : "#c62828";
}

/* ------------------------------ вход и регистрация ---------------------- */
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: { email: form.get("email"), password: form.get("password") },
    });
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem("pf_token", state.token);
    await startWorkspace();
  } catch (error) {
    showMessage($("#auth-message"), error.message);
  }
});

$("#register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api("/auth/register", {
      method: "POST",
      body: {
        full_name: form.get("full_name"),
        email: form.get("email"),
        password: form.get("password"),
      },
    });
    showMessage($("#auth-message"), "Пользователь создан, можно входить", true);
  } catch (error) {
    showMessage($("#auth-message"), error.message);
  }
});

$("#logout").addEventListener("click", () => {
  state.token = null;
  state.user = null;
  localStorage.removeItem("pf_token");
  $("#workspace").classList.add("hidden");
  $("#auth-screen").classList.remove("hidden");
  $("#user-box").classList.add("hidden");
});

/* ------------------------------ рабочая область ------------------------- */
async function startWorkspace() {
  if (!state.user) {
    const me = await api("/users/me");
    state.user = me.user;
  }
  $("#auth-screen").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  $("#user-box").classList.remove("hidden");
  $("#user-name").textContent = state.user.full_name;
  $("#user-role").textContent = state.user.role;
  const canCreate = state.user.role !== "executor";
  $("#task-create-box").classList.toggle("hidden", !canCreate);
  await loadDictionaries();
  await loadTasks();
  await loadProjects();
  await loadReports();
}

async function loadDictionaries() {
  const projects = await api("/projects?size=100");
  state.projects = projects.items;
  fillSelect($("#filter-project"), state.projects, "все проекты", "");
  fillSelect($("#task-project"), state.projects, null, "");
  fillSelect($("#report-project"), state.projects, null, "");
  try {
    const users = await api("/users");
    state.users = users.items.filter((u) => u.is_active);
  } catch (error) {
    state.users = [state.user];
  }
  fillSelect($("#task-assignee"), state.users, "не назначен", "");
  fillSelect($("#report-assignee"), state.users, null, "");
}

function fillSelect(select, items, placeholder, valueField) {
  select.innerHTML = "";
  if (placeholder !== null) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = placeholder;
    select.appendChild(option);
  }
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name ? `${item.code} — ${item.name}` : item.full_name;
    select.appendChild(option);
  });
}

/* ------------------------------ задачи ---------------------------------- */
async function loadTasks() {
  const params = new URLSearchParams();
  const status = $("#filter-status").value;
  const project = $("#filter-project").value;
  if (status) params.set("status", status);
  if (project) params.set("project_id", project);
  const data = await api("/tasks?" + params.toString());
  const container = $("#tasks-list");
  if (!data.items.length) {
    container.innerHTML = "<p>Задач пока нет.</p>";
    return;
  }
  const rows = data.items.map((task) => {
    const actions = task.actions
      .map((action) => `<button class="small" data-task="${task.id}" data-status="${action.status}">${action.caption}</button>`)
      .join("");
    return `<tr>
      <td>${task.id}</td>
      <td>${escapeHtml(task.title)}${task.overdue ? ' <span class="overdue">просрочена</span>' : ""}</td>
      <td>${task.assignee ? escapeHtml(task.assignee.full_name) : "—"}</td>
      <td class="status status-${task.status}">${task.status_title}</td>
      <td>${task.due_date || "—"}</td>
      <td>${actions || "—"}</td>
    </tr>`;
  }).join("");
  container.innerHTML = `<table>
    <tr><th>№</th><th>Задача</th><th>Исполнитель</th><th>Статус</th><th>Срок</th><th>Действия</th></tr>
    ${rows}</table>`;
  container.querySelectorAll("button[data-task]").forEach((button) => {
    button.addEventListener("click", () => changeStatus(button.dataset.task, button.dataset.status));
  });
}

async function changeStatus(taskId, status) {
  let comment = "";
  if (status === "rejected") {
    comment = prompt("Причина отклонения (обязательно):") || "";
    if (!comment) return;
  }
  try {
    await api(`/tasks/${taskId}/status`, { method: "PATCH", body: { status, comment } });
    await loadTasks();
  } catch (error) {
    alert(error.message);
  }
}

$("#reload-tasks").addEventListener("click", loadTasks);
$("#filter-status").addEventListener("change", loadTasks);
$("#filter-project").addEventListener("change", loadTasks);

$("#task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const body = {
    project_id: Number(form.get("project_id")),
    title: form.get("title"),
    priority: form.get("priority"),
  };
  if (form.get("assignee_id")) body.assignee_id = Number(form.get("assignee_id"));
  if (form.get("due_date")) body.due_date = form.get("due_date");
  try {
    await api("/tasks", { method: "POST", body });
    event.target.reset();
    await loadTasks();
  } catch (error) {
    alert(error.message);
  }
});

/* ------------------------------ проекты --------------------------------- */
async function loadProjects() {
  const data = await api("/projects?size=100");
  $("#projects-list").innerHTML = `<table>
    <tr><th>Код</th><th>Название</th><th>Статус</th><th>Период</th></tr>
    ${data.items.map((project) => `<tr>
      <td>${project.code}</td><td>${escapeHtml(project.name)}</td>
      <td>${project.status}</td>
      <td>${project.start_date || "—"} — ${project.end_date || "—"}</td></tr>`).join("")}
  </table>`;
}

$("#project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    await api("/projects", {
      method: "POST",
      body: {
        code: form.get("code"),
        name: form.get("name"),
        description: form.get("description"),
      },
    });
    event.target.reset();
    await loadDictionaries();
    await loadProjects();
  } catch (error) {
    alert(error.message);
  }
});

/* ------------------------------ отчёты ---------------------------------- */
$("#report-type").addEventListener("change", () => {
  const value = $("#report-type").value;
  $("#report-project-label").classList.toggle("hidden", value !== "by_project");
  $("#report-assignee-label").classList.toggle("hidden", value !== "by_assignee");
});

$("#report-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const body = {
    report_type: form.get("report_type"),
    format: form.get("format"),
  };
  if (form.get("project_id") && body.report_type === "by_project") {
    body.project_id = Number(form.get("project_id"));
  }
  if (form.get("assignee_id") && body.report_type === "by_assignee") {
    body.assignee_id = Number(form.get("assignee_id"));
  }
  if (form.get("period_from")) body.period_from = form.get("period_from");
  if (form.get("period_to")) body.period_to = form.get("period_to");
  try {
    const data = await api("/reports", { method: "POST", body });
    showMessage($("#report-message"),
      `Отчёт №${data.report.id} сформирован, строк: ${data.report.rows_count}`, true);
    await loadReports();
  } catch (error) {
    showMessage($("#report-message"), error.message);
  }
});

async function loadReports() {
  const data = await api("/reports");
  const container = $("#reports-list");
  if (!data.items.length) {
    container.innerHTML = "<p>Отчёты ещё не формировались.</p>";
    return;
  }
  container.innerHTML = `<table>
    <tr><th>№</th><th>Вид</th><th>Формат</th><th>Строк</th><th>Создан</th><th>Файл</th></tr>
    ${data.items.map((report) => `<tr>
      <td>${report.id}</td><td>${report.title}</td><td>${report.format}</td>
      <td>${report.rows_count}</td><td>${report.created_at.replace("T", " ")}</td>
      <td><a href="${report.download_url}?token=${state.token}" target="_blank">скачать</a></td>
    </tr>`).join("")}
  </table><p class="hint">Ссылка на файл откроется в новой вкладке.</p>`;
}

/* ------------------------------ вкладки ---------------------------------- */
document.querySelectorAll(".tabs button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    ["tasks", "projects", "reports"].forEach((tab) => {
      $("#tab-" + tab).classList.toggle("hidden", tab !== button.dataset.tab);
    });
  });
});

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : text;
  return div.innerHTML;
}

if (state.token) {
  startWorkspace().catch(() => {
    state.token = null;
    localStorage.removeItem("pf_token");
  });
}
