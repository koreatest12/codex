"use strict";

let csrfToken = "";
let editing = null;
let offset = 0;
let quiz = [];
let quizIndex = 0;
const PAGE_SIZE = 20;
const $ = id => document.getElementById(id);

function node(tag, text = "", className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function notify(message, error = false) {
  const box = $("message");
  box.textContent = message;
  box.className = error ? "notice error" : "notice";
}

async function api(url, method = "GET", body = null) {
  const options = { method, credentials: "same-origin", headers: {} };
  if (method !== "GET") {
    options.headers["Content-Type"] = "application/json";
    options.headers["X-Question-CSRF"] = csrfToken;
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); } catch { throw new Error("서버 응답을 읽지 못했습니다."); }
  if (!response.ok) throw new Error(data.error || "요청이 거부되었습니다.");
  return data;
}

async function guarded(fn) {
  try { await fn(); } catch (error) { notify(error.message, true); }
}

function fillSubjects(id, subjects) {
  const select = $(id);
  for (const subject of subjects) {
    const option = node("option", subject);
    option.value = subject;
    select.append(option);
  }
}

function setPartFields() {
  const written = $("exam-part").value === "실기";
  $("written-field").hidden = !written;
  $("multiple-choice-fields").hidden = written;
}

function resetEditor() {
  editing = null;
  $("question-form").reset();
  $("exam-part").value = "필기";
  setPartFields();
  $("edit-meta").textContent = "새 문제 작성 중 (출제 승인 전에는 미공개)";
  $("publish").disabled = true;
  $("archive").disabled = true;
}

function editQuestion(item) {
  editing = item;
  $("exam-part").value = item.exam_part;
  $("subject").value = item.subject;
  $("topic").value = item.topic;
  $("difficulty").value = String(item.difficulty);
  $("prompt").value = item.prompt;
  $("options").value = item.options.join("\n");
  $("correct-index").value = String(item.correct_index ?? 0);
  $("model-answer").value = item.model_answer || "";
  $("explanation").value = item.explanation;
  $("source-url").value = item.source_url;
  $("edit-meta").textContent =
    "ID: " + item.id + " · 상태: " + item.status + " · 개정: " + item.revision;
  $("publish").disabled = item.status === "published";
  $("archive").disabled = item.status === "archived";
  setPartFields();
  $("editor-heading").scrollIntoView({ behavior: "smooth" });
}

function payloadFromForm() {
  const written = $("exam-part").value === "실기";
  return {
    exam_part: $("exam-part").value,
    subject: $("subject").value,
    kind: written ? "written" : "multiple_choice",
    topic: $("topic").value.trim(),
    prompt: $("prompt").value.trim(),
    options: written ? [] : $("options").value.split(/\r?\n/).map(x => x.trim()),
    correct_index: written ? null : Number($("correct-index").value),
    model_answer: written ? $("model-answer").value.trim() : "",
    explanation: $("explanation").value.trim(),
    source_url: $("source-url").value.trim(),
    difficulty: Number($("difficulty").value)
  };
}

function filters() {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if ($("filter-part").value) params.set("exam_part", $("filter-part").value);
  if ($("filter-subject").value) params.set("subject", $("filter-subject").value);
  if ($("filter-status").value) params.set("status", $("filter-status").value);
  return params;
}

async function loadQuestions() {
  const data = await api("/api/questions?" + filters().toString());
  const area = $("question-list");
  area.replaceChildren();
  if (!data.items.length) area.append(node("p", "등록된 문제가 없습니다.", "meta"));
  data.items.forEach(item => {
    const card = node("article", "", "question-card");
    const header = node("div", item.exam_part + " · " + item.subject + " · " +
      item.topic + " · 난이도 " + item.difficulty + " · " + item.status, "meta");
    const title = node("p", item.prompt, "question-prompt");
    const action = node("button", "열어서 편집");
    action.type = "button";
    action.addEventListener("click", () => editQuestion(item));
    card.append(header, title, action);
    area.append(card);
  });
  $("question-total").textContent = "총 " + data.total + "문항";
  $("page-label").textContent = (offset + 1) + "–" +
    Math.min(offset + PAGE_SIZE, data.total) + " / " + data.total;
  $("prev").disabled = offset === 0;
  $("next").disabled = offset + PAGE_SIZE >= data.total;
}

async function saveQuestion(event) {
  event.preventDefault();
  const payload = payloadFromForm();
  let item;
  if (editing) {
    payload.expected_revision = editing.revision;
    item = await api("/api/questions/" + editing.id, "PATCH", payload);
  } else {
    item = await api("/api/questions", "POST", payload);
  }
  editQuestion(item);
  notify("문제가 초안/편집 상태로 저장되었습니다. 검토 후 출제를 승인하세요.");
  await loadQuestions();
}

async function publishQuestion() {
  if (!editing || !window.confirm("문제와 정답·해설·출처를 확인했습니까? 승인하면 모의학습에 출제됩니다.")) return;
  editing = await api("/api/questions/" + editing.id, "PATCH", {
    expected_revision: editing.revision, status: "published", reviewed: true
  });
  editQuestion(editing);
  await loadQuestions();
  notify("검토 완료 문제로 등록되었습니다.");
}

async function archiveQuestion() {
  if (!editing || !window.confirm("문제를 보관 처리하시겠습니까? 과거 풀이 기록은 유지됩니다.")) return;
  editing = await api("/api/questions/" + editing.id, "DELETE", {
    expected_revision: editing.revision
  });
  editQuestion(editing);
  await loadQuestions();
  notify("문제가 보관 처리되었습니다.");
}

function resultCard(data) {
  const card = node("section", "", "result");
  const text = data.manual_review_required
    ? "서술형 — 자동 채점되지 않습니다. 아래 모범답안을 보고 스스로 평가하세요."
    : (data.is_correct ? "정답입니다." : "오답입니다. 다음 해설을 확인하세요.");
  card.append(node("h3", text));
  if (data.correct_index !== null) {
    card.append(node("p", "정답 선택지: " + (data.correct_index + 1) + "번"));
  }
  if (data.model_answer !== null) {
    card.append(node("p", "학습용 모범답안: " + data.model_answer));
  }
  card.append(node("p", "해설: " + data.explanation));
  if (data.manual_review_required) {
    const yes = node("button", "자체 평가: 이해함");
    const no = node("button", "자체 평가: 재학습 필요", "secondary");
    for (const [button, correct] of [[yes, true], [no, false]]) {
      button.addEventListener("click", () => guarded(async () => {
        await api("/api/questions/attempts/" + data.attempt_id + "/review",
          "POST", { is_correct: correct });
        yes.disabled = true; no.disabled = true;
        notify(correct ? "서술형 이해 완료로 기록했습니다." : "서술형 복습 대상으로 기록했습니다.");
        await loadHistory();
      }));
    }
    card.append(yes, no);
  }
  return card;
}

async function showQuiz() {
  const area = $("practice-box");
  area.replaceChildren();
  if (quizIndex >= quiz.length) {
    area.append(node("p", "모든 문제를 풀었습니다. 풀이 기록과 오답을 확인하세요."));
    await loadHistory();
    return;
  }
  const q = quiz[quizIndex];
  area.append(node("div", "문제 " + (quizIndex + 1) + " / " + quiz.length +
    " · " + q.exam_part + " · " + q.subject + " · " + q.topic, "meta"));
  area.append(node("h3", q.prompt));
  const form = node("form");
  let input;
  if (q.kind === "multiple_choice") {
    q.options.forEach((answer, index) => {
      const label = node("label", "", "option");
      const radio = document.createElement("input");
      radio.type = "radio"; radio.name = "choice"; radio.value = String(index);
      if (index === 0) radio.required = true;
      label.append(radio, document.createTextNode(" " + (index + 1) + ". " + answer));
      form.append(label);
    });
  } else {
    input = document.createElement("textarea");
    input.rows = 5;
    input.maxLength = 4000;
    input.required = true;
    input.placeholder = "정답 근거와 핵심 개념을 서술하세요.";
    form.append(input);
  }
  const submit = node("button", "답안 제출");
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", event => {
    event.preventDefault();
    guarded(async () => {
      const body = q.kind === "multiple_choice"
        ? { question_id: q.id, selected_choice: Number(form.querySelector('input[name="choice"]:checked').value) }
        : { question_id: q.id, written_response: input.value };
      const result = await api("/api/questions/attempts", "POST", body);
      form.remove();
      area.append(resultCard(result));
      const next = node("button", quizIndex + 1 === quiz.length ? "학습 종료" : "다음 문제");
      next.type = "button";
      next.addEventListener("click", () => guarded(async () => { quizIndex++; await showQuiz(); }));
      area.append(next);
      await loadHistory();
    });
  });
  area.append(form);
}

async function startPractice() {
  const params = new URLSearchParams({ limit: $("practice-limit").value });
  if ($("practice-part").value) params.set("exam_part", $("practice-part").value);
  if ($("practice-subject").value) params.set("subject", $("practice-subject").value);
  const data = await api("/api/questions/practice?" + params.toString());
  quiz = data.items;
  quizIndex = 0;
  if (!quiz.length) {
    $("practice-box").replaceChildren(node("p", "검토 완료된 문제가 없습니다. 문제를 등록하고 승인하세요."));
    return;
  }
  await showQuiz();
}

async function loadHistory() {
  const data = await api("/api/questions/attempts");
  $("attempt-stats").textContent = "풀이 " + data.stats.total + "회 · 정답/이해 " +
    data.stats.correct + "회 · 서술형 미평가 " + data.stats.ungraded + "회";
  const area = $("attempt-history");
  area.replaceChildren();
  data.items.forEach(item => {
    let status = item.is_correct === null ? "미평가" : (item.is_correct ? "정답/이해" : "오답/복습");
    area.append(node("p", item.created_at + " · " + item.subject + " · " + item.topic +
      " · " + status, "history-item"));
  });
}

async function initialize() {
  const info = await api("/api/questions/session");
  csrfToken = info.csrf_token;
  ["subject", "filter-subject", "practice-subject"].forEach(id => fillSubjects(id, info.subjects));
  $("exam-part").addEventListener("change", setPartFields);
  $("question-form").addEventListener("submit", e => guarded(() => saveQuestion(e)));
  $("new").addEventListener("click", resetEditor);
  $("publish").addEventListener("click", () => guarded(publishQuestion));
  $("archive").addEventListener("click", () => guarded(archiveQuestion));
  $("load").addEventListener("click", () => guarded(async () => { offset = 0; await loadQuestions(); }));
  $("prev").addEventListener("click", () => guarded(async () => { offset = Math.max(0, offset - PAGE_SIZE); await loadQuestions(); }));
  $("next").addEventListener("click", () => guarded(async () => { offset += PAGE_SIZE; await loadQuestions(); }));
  $("start-practice").addEventListener("click", () => guarded(startPractice));
  $("refresh-attempts").addEventListener("click", () => guarded(loadHistory));
  resetEditor();
  await Promise.all([loadQuestions(), loadHistory()]);
  notify("문제은행 서버 연결 완료 · 관리자 전용입니다.");
}
guarded(initialize);
