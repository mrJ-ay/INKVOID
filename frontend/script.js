const API_URL = window.INKVOID_API_URL || "http://127.0.0.1:8000";
const TOKEN_KEY = "inkvoid_token";
const DRAFT_KEY = "inkvoid_writer_draft_v1";
let works = [];
let allWorks = [];
let currentWork = null;
let activeChapterId = null;
let readingWork = null;
let readingChapterId = null;
let currentUser = null;
let saveTimer = null;
let toastTimer = null;
let isSaving = false;
let queuedSave = false;

const $ = id => document.getElementById(id);
const token = () => localStorage.getItem(TOKEN_KEY);
const makeId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  let data = null;
  try { data = await response.json(); } catch {}
  if (!response.ok) throw new Error(data?.detail || data?.message || "요청을 처리하지 못했어요.");
  return data;
}

function notify(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2600);
}

function showPage(id) {
  ["explorePage", "libraryPage", "editorPage", "loginPage", "readerPage"].forEach(page => $(page).hidden = page !== id);
  $("exploreNav").classList.toggle("active", id === "explorePage");
  $("libraryNav").classList.toggle("active", id === "libraryPage");
}

function showLibrary() {
  if (!token()) { showLogin(); notify("내 서재를 보려면 로그인해 주세요."); return; }
  showPage("libraryPage");
  renderLibrary();
}

function showExplore() {
  showPage("explorePage");
  renderExplore();
}

function showLogin() { showPage("loginPage"); }

function decodeWork(record) {
  let saved;
  try { saved = JSON.parse(record.content || ""); } catch { saved = null; }
  if (saved?.format === "fakepress-novel-v1" && Array.isArray(saved.chapters) && saved.chapters.length) {
    return { ...record, summary: record.subtitle || "", chapters: saved.chapters, isNovel: true };
  }
  return { ...record, summary: record.subtitle || "", chapters: [{ id: makeId(), title: "첫 번째 장", body: record.content || "" }], isNovel: false };
}

function encodeWork(work) {
  return JSON.stringify({ format: "fakepress-novel-v1", chapters: work.chapters });
}

async function loadWorks() {
  try {
    const data = await request("/articles");
    const records = Array.isArray(data) ? data : (data?.articles || []);
    allWorks = records.map(decodeWork).filter(item => item.isNovel);
    works = allWorks.filter(item => currentUser && Number(item.owner_id) === Number(currentUser.id));
    renderExplore();
    renderLibrary();
  } catch (error) { notify(error.message); }
}

function renderExplore() {
  const query = ($("exploreSearch")?.value || "").trim().toLocaleLowerCase();
  const filtered = allWorks.filter(work => `${work.title} ${work.summary} ${work.author}`.toLocaleLowerCase().includes(query));
  $("publicCount").textContent = String(allWorks.length);
  const grid = $("publicGrid");
  if (!filtered.length) {
    grid.innerHTML = `<div class="empty-state">${allWorks.length ? "검색한 이야기가 없어요." : "아직 공개된 이야기가 없어요.\n첫 작품을 올려 이 서가를 채워보세요."}</div>`;
    return;
  }
  grid.innerHTML = filtered.map((work, index) => {
    const total = work.chapters.reduce((sum, chapter) => sum + (chapter.body || "").length, 0);
    return `<article class="work-card" onclick="openReader(${Number(work.id)})"><div class="work-cover cover-${index % 5 + 1}"></div><h3>${escapeHtml(work.title || "제목 없는 작품")}</h3><p>${escapeHtml(work.summary || "작가가 아직 소개를 적지 않았어요.")}</p><div class="work-meta"><strong>${work.chapters.length}회차 · ${total.toLocaleString()}자</strong><span>${escapeHtml(work.author || "작가 미상")}</span></div></article>`;
  }).join("");
}

function openReader(id) {
  readingWork = allWorks.find(item => Number(item.id) === Number(id));
  if (!readingWork) return;
  readingChapterId = readingWork.chapters[0]?.id;
  $("readerTitle").textContent = readingWork.title || "제목 없는 작품";
  $("readerAuthor").textContent = readingWork.author ? `BY ${readingWork.author}` : "INKVOID STORY";
  $("readerSummary").textContent = readingWork.summary || "";
  renderReaderChapter();
  showPage("readerPage");
}

function renderReaderChapter() {
  if (!readingWork) return;
  const index = readingWork.chapters.findIndex(chapter => chapter.id === readingChapterId);
  const chapter = readingWork.chapters[index];
  if (!chapter) return;
  $("readerChapterTitle").textContent = chapter.title || `제 ${index + 1} 장`;
  $("readerOrdinal").textContent = `CHAPTER ${String(index + 1).padStart(2, "0")}`;
  $("readerBody").textContent = chapter.body || "아직 이 회차에는 글이 없어요.";
  $("readerChapterList").innerHTML = readingWork.chapters.map((item, itemIndex) => `<button class="reader-chapter ${item.id === readingChapterId ? "selected" : ""}" onclick="selectReaderChapter('${escapeHtml(item.id)}')">${String(itemIndex + 1).padStart(2, "0")} · ${escapeHtml(item.title || "제목 없는 장")}</button>`).join("");
  $("previousChapter").disabled = index <= 0;
  $("nextChapter").disabled = index >= readingWork.chapters.length - 1;
}

function selectReaderChapter(id) {
  readingChapterId = id;
  renderReaderChapter();
}

function moveChapter(direction) {
  if (!readingWork) return;
  const index = readingWork.chapters.findIndex(chapter => chapter.id === readingChapterId);
  const next = readingWork.chapters[index + direction];
  if (next) selectReaderChapter(next.id);
}

function renderLibrary() {
  const query = ($("searchInput")?.value || "").trim().toLocaleLowerCase();
  const filtered = works.filter(work => `${work.title} ${work.summary}`.toLocaleLowerCase().includes(query));
  $("workCount").textContent = String(works.length);
  const grid = $("workGrid");
  if (!filtered.length) {
    grid.innerHTML = `<div class="empty-state">${works.length ? "검색한 작품이 없어요." : "아직 작품이 없어요.\n첫 이야기를 시작해 볼까요?"}</div>`;
    return;
  }
  grid.innerHTML = filtered.map((work, index) => {
    const total = work.chapters.reduce((sum, chapter) => sum + (chapter.body || "").length, 0);
    const date = work.updated_at ? new Date(work.updated_at).toLocaleDateString("ko-KR", { year:"numeric", month:"long", day:"numeric" }) : "방금 작성";
    return `<article class="work-card" onclick="openWork(${Number(work.id)})"><div class="work-cover cover-${index % 5 + 1}"></div><h3>${escapeHtml(work.title || "제목 없는 작품")}</h3><p>${escapeHtml(work.summary || "아직 소개가 없어요.")}</p><div class="work-meta"><strong>${work.chapters.length}회차 · ${total.toLocaleString()}자</strong><span>${escapeHtml(date)}</span></div></article>`;
  }).join("");
}

function freshWork(title) {
  return { id: null, title, summary: "", author: currentUser?.nickname || "", date: new Date().toISOString().slice(0, 10), chapters: [{ id: makeId(), title: "첫 번째 장", body: "" }], isNovel: true };
}

async function newWork() {
  if (!token()) { showLogin(); notify("로그인하면 작품을 쓸 수 있어요."); return; }
  const title = window.prompt("새 작품의 제목을 지어주세요.", "새 작품");
  if (!title?.trim()) return;
  const work = freshWork(title.trim());
  try {
    const result = await request("/articles", { method:"POST", body:JSON.stringify({ title:work.title, subtitle:"", author:work.author, date:work.date, content:encodeWork(work) }) });
    const record = result?.article || result;
    currentWork = { ...work, id:record.id, owner_id:record.owner_id, updated_at:record.updated_at };
    activeChapterId = currentWork.chapters[0].id;
    works.unshift(currentWork);
    allWorks.unshift(currentWork);
    renderExplore();
    openEditor();
    notify("새 작품을 서재에 만들었어요.");
  } catch (error) { notify(error.message); }
}

function openWork(id) {
  const work = works.find(item => Number(item.id) === Number(id));
  if (!work) return;
  currentWork = JSON.parse(JSON.stringify(work));
  const localDraft = readDraft();
  if (localDraft && Number(localDraft.id) === Number(id)) currentWork = localDraft;
  activeChapterId = currentWork.chapters[0]?.id;
  openEditor();
}

function readDraft() {
  try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); } catch { return null; }
}

function openEditor() {
  if (!currentWork) return;
  showPage("editorPage");
  $("workTitle").value = currentWork.title || "";
  $("workSummary").value = currentWork.summary || "";
  renderChapters();
  renderActiveChapter();
  updateWordCount();
  $("saveStatus").textContent = "저장됨";
}

function renderChapters() {
  const list = $("chapterList");
  list.innerHTML = currentWork.chapters.map((chapter, index) => `<div class="chapter-item ${chapter.id === activeChapterId ? "selected" : ""}" onclick="selectChapter('${escapeHtml(chapter.id)}')"><span class="chapter-number">${String(index + 1).padStart(2, "0")}</span><span class="chapter-name">${escapeHtml(chapter.title || "제목 없는 장")}</span></div>`).join("");
  $("chapterOrdinal").textContent = `CHAPTER ${String(Math.max(0, currentWork.chapters.findIndex(item => item.id === activeChapterId) + 1)).padStart(2, "0")}`;
}

function renderActiveChapter() {
  const chapter = currentWork?.chapters.find(item => item.id === activeChapterId);
  if (!chapter) return;
  $("chapterTitle").value = chapter.title || "";
  $("chapterBody").value = chapter.body || "";
}

function selectChapter(id) {
  captureActiveChapter();
  activeChapterId = id;
  renderChapters();
  renderActiveChapter();
}

function captureActiveChapter() {
  if (!currentWork) return;
  currentWork.title = $("workTitle").value;
  currentWork.summary = $("workSummary").value;
  const chapter = currentWork.chapters.find(item => item.id === activeChapterId);
  if (chapter) { chapter.title = $("chapterTitle").value; chapter.body = $("chapterBody").value; }
}

function addChapter() {
  captureActiveChapter();
  const chapter = { id:makeId(), title:`第 ${currentWork.chapters.length + 1} 장`, body:"" };
  currentWork.chapters.push(chapter);
  activeChapterId = chapter.id;
  renderChapters(); renderActiveChapter(); updateWordCount(); queueSave();
  $("chapterTitle").focus();
}

function updateWordCount() {
  if (!currentWork) return;
  captureActiveChapter();
  const count = currentWork.chapters.reduce((sum, chapter) => sum + (chapter.body || "").length, 0);
  $("wordCount").textContent = count.toLocaleString();
  renderChapters();
}

function queueSave() {
  if (!currentWork) return;
  captureActiveChapter();
  localStorage.setItem(DRAFT_KEY, JSON.stringify(currentWork));
  $("saveStatus").textContent = "저장 중…";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveWork(false), 1100);
}

async function saveWork(manual) {
  if (!currentWork || !currentWork.id) return;
  captureActiveChapter();
  localStorage.setItem(DRAFT_KEY, JSON.stringify(currentWork));
  if (isSaving) { queuedSave = true; return; }
  isSaving = true;
  try {
    await request(`/articles/${currentWork.id}`, { method:"PUT", body:JSON.stringify({ title:currentWork.title.trim() || "제목 없는 작품", subtitle:currentWork.summary || "", author:currentWork.author || currentUser?.nickname || "", date:new Date().toISOString().slice(0, 10), content:encodeWork(currentWork) }) });
    currentWork.updated_at = new Date().toISOString();
    const index = works.findIndex(item => Number(item.id) === Number(currentWork.id));
    if (index >= 0) works[index] = JSON.parse(JSON.stringify(currentWork));
    const publicIndex = allWorks.findIndex(item => Number(item.id) === Number(currentWork.id));
    if (publicIndex >= 0) allWorks[publicIndex] = JSON.parse(JSON.stringify(currentWork));
    renderExplore();
    localStorage.setItem(DRAFT_KEY, JSON.stringify(currentWork));
    $("saveStatus").textContent = "모든 변경사항 저장됨";
    $("lastSaved").textContent = `저장 ${new Date().toLocaleTimeString("ko-KR", { hour:"2-digit", minute:"2-digit" })}`;
    if (manual) notify("작품을 저장했어요.");
  } catch (error) {
    $("saveStatus").textContent = "기기에 임시 저장됨";
    if (manual) notify(`서버 저장 실패: ${error.message}`);
  } finally {
    isSaving = false;
    if (queuedSave) { queuedSave = false; saveWork(false); }
  }
}

async function registerUser() {
  const nickname = $("loginNickname").value.trim();
  const password = $("loginPassword").value;
  if (!nickname || !password) { notify("닉네임과 비밀번호를 입력해 주세요."); return; }
  try { const result = await request("/auth/register", { method:"POST", body:JSON.stringify({ nickname, password }) }); notify(result?.message || "가입이 완료됐어요. 로그인해 주세요."); }
  catch (error) { notify(error.message); }
}

async function login() {
  const nickname = $("loginNickname").value.trim();
  const password = $("loginPassword").value;
  if (!nickname || !password) { notify("닉네임과 비밀번호를 입력해 주세요."); return; }
  try {
    const result = await request("/auth/login", { method:"POST", body:JSON.stringify({ nickname, password }) });
    localStorage.setItem(TOKEN_KEY, result.access_token || result.token);
    await checkLogin();
    await loadWorks();
    showLibrary();
    notify("로그인했어요. 이어서 써볼까요?");
  } catch (error) { notify(error.message); }
}

async function checkLogin() {
  if (!token()) return;
  try {
    currentUser = await request("/auth/me");
    $("userName").textContent = currentUser.nickname || "작가";
    $("loginButton").hidden = true;
    $("logoutButton").hidden = false;
  } catch {
    localStorage.removeItem(TOKEN_KEY);
    currentUser = null;
  }
}

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem("inkvoid_current_user");
  currentUser = null; works = []; currentWork = null;
  $("userName").textContent = ""; $("loginButton").hidden = false; $("logoutButton").hidden = true;
  showExplore(); notify("로그아웃했어요.");
}

document.addEventListener("DOMContentLoaded", async () => {
  ["workTitle", "workSummary", "chapterTitle", "chapterBody"].forEach(id => {
    $(id).addEventListener("input", () => { updateWordCount(); queueSave(); });
  });
  $("loginPassword").addEventListener("keydown", event => { if (event.key === "Enter") login(); });
  await checkLogin();
  await loadWorks();
  showExplore();
});

Object.assign(window, { showExplore, showLibrary, showLogin, newWork, openWork, selectChapter, addChapter, saveWork, openReader, selectReaderChapter, moveChapter, login, registerUser, logout });
