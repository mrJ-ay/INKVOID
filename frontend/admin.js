const API_URL = window.INKVOID_API_URL || "http://127.0.0.1:8000";


const token =
    localStorage.getItem(
        "inkvoid_token"
    );


const currentUser =
    JSON.parse(
        localStorage.getItem(
            "inkvoid_current_user"
        ) || "null"
    );


// =========================================================
// 로그인 확인
// =========================================================

if (
    !token ||
    !currentUser
) {

    alert(
        "로그인이 필요합니다."
    );

    location.href =
        "index.html";

}
else if (
    Number(
        currentUser.is_admin
    ) !== 1
) {

    alert(
        "관리자만 접근할 수 있습니다."
    );

    location.href =
        "index.html";

}
else {

    const nicknameElement =
        document.getElementById(
            "adminNickname"
        );

    if (nicknameElement) {

        nicknameElement.textContent =
            `${currentUser.nickname} 관리자`;

    }

    loadUsers();
    loadBannedWords();
    loadArticles();
}


// =========================================================
// 공통 헤더
// =========================================================

function getHeaders() {

    return {

        "Authorization":
            `Bearer ${token}`,

        "Content-Type":
            "application/json"

    };

}


// =========================================================
// 메시지
// =========================================================

function showMessage(
    message
) {

    const messageBox =
        document.getElementById(
            "message"
        );

    if (!messageBox) return;

    messageBox.textContent =
        message;

    messageBox.style.display =
        "block";

    setTimeout(
        () => {

            messageBox.textContent =
                "";

            messageBox.style.display =
                "none";

        },
        3000
    );

}


// =========================================================
// USERS
// =========================================================

async function loadUsers() {

    try {

        const response =
            await fetch(
                `${API_URL}/admin/users`,
                {
                    method: "GET",
                    headers: getHeaders()
                }
            );

        const data =
            await response.json();

        if (!response.ok) {

            throw new Error(
                data.detail ||
                "사용자 목록을 불러오지 못했습니다."
            );

        }

        renderUsers(
            data
        );

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "사용자 목록을 불러오는 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// RENDER USERS
// =========================================================

function renderUsers(
    users
) {

    const userList =
        document.getElementById(
            "userList"
        );

    if (!userList) return;

    if (!users.length) {

        userList.innerHTML =
            "<p class='empty'>등록된 사용자가 없습니다.</p>";

        return;

    }

    userList.innerHTML =
        users
            .map(
                user =>
                    renderUser(
                        user
                    )
            )
            .join("");

}


// =========================================================
// RENDER USER
// =========================================================

function renderUser(
    user
) {

    const isAdmin =
        Number(
            user.is_admin
        ) === 1;

    const isBanned =
        Number(
            user.is_banned
        ) === 1;


    return `

        <div class="article-row">

            <div class="article-info">

                <div class="article-title">
                    ${escapeHtml(
                        user.nickname
                    )}
                </div>

                <div class="article-meta">

                    ID:
                    ${user.id}

                    &nbsp; | &nbsp;

                    ${
                        isAdmin
                            ? '<span class="status-admin">관리자</span>'
                            : "일반 사용자"
                    }

                    &nbsp; | &nbsp;

                    ${
                        isBanned
                            ? '<span class="status-banned">🚫 정지됨</span>'
                            : '<span class="status-normal">정상</span>'
                    }

                </div>

            </div>


            <div style="
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
            ">

                <button
                    class="${
                        isBanned
                            ? "unban"
                            : "ban"
                    }"
                    onclick="
                        toggleBan(
                            ${user.id},
                            ${isBanned}
                        )
                    "
                >
                    ${
                        isBanned
                            ? "정지 해제"
                            : "정지"
                    }
                </button>


                <button
                    class="${
                        isAdmin
                            ? "remove-admin"
                            : "admin"
                    }"
                    onclick="
                        toggleAdmin(
                            ${user.id},
                            ${isAdmin}
                        )
                    "
                >
                    ${
                        isAdmin
                            ? "관리자 해제"
                            : "관리자 지정"
                    }
                </button>

            </div>

        </div>

    `;

}


// =========================================================
// BAN / UNBAN
// =========================================================

async function toggleBan(
    userId,
    isBanned
) {

    try {

        const endpoint =
            isBanned
                ? `/admin/unban/${userId}`
                : `/admin/ban/${userId}`;


        const response =
            await fetch(
                `${API_URL}${endpoint}`,
                {
                    method: "POST",
                    headers: getHeaders()
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "사용자 정지 처리에 실패했습니다."
            );

        }


        showMessage(
            data.message ||
            (
                isBanned
                    ? "사용자 정지가 해제되었습니다."
                    : "사용자가 정지되었습니다."
            )
        );


        await loadUsers();

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "사용자 정지 처리 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// ADMIN / REMOVE ADMIN
// =========================================================

async function toggleAdmin(
    userId,
    isAdmin
) {

    try {

        const endpoint =
            isAdmin
                ? `/admin/remove-admin/${userId}`
                : `/admin/make-admin/${userId}`;


        const response =
            await fetch(
                `${API_URL}${endpoint}`,
                {
                    method: "POST",
                    headers: getHeaders()
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "관리자 권한 처리에 실패했습니다."
            );

        }


        showMessage(
            data.message ||
            (
                isAdmin
                    ? "관리자 권한이 제거되었습니다."
                    : "관리자로 지정되었습니다."
            )
        );


        await loadUsers();

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "관리자 권한 처리 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// BANNED WORDS
// =========================================================

async function loadBannedWords() {

    try {

        const response =
            await fetch(
                `${API_URL}/admin/banned-words`,
                {
                    method: "GET",
                    headers: getHeaders()
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "금지어 목록을 불러오지 못했습니다."
            );

        }


        renderBannedWords(
            data
        );

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "금지어 목록을 불러오는 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// RENDER BANNED WORDS
// =========================================================

function renderBannedWords(
    words
) {

    const list =
        document.getElementById(
            "bannedWordList"
        );

    if (!list) return;


    if (!words.length) {

        list.innerHTML =
            `
            <p class="empty">
                등록된 금지어가 없습니다.
            </p>
            `;

        return;

    }


    list.innerHTML =
        words
            .map(
                item => `

                    <div class="article-row">

                        <div class="article-info">

                            <div class="article-title">
                                🚫
                                ${escapeHtml(
                                    item.word
                                )}
                            </div>

                            <div class="article-meta">
                                금지어 ID:
                                ${item.id}
                            </div>

                        </div>


                        <button
                            class="delete"
                            onclick="
                                deleteBannedWord(
                                    ${item.id},
                                    '${escapeJs(
                                        item.word
                                    )}'
                                )
                            "
                        >
                            금지어 삭제
                        </button>

                    </div>

                `
            )
            .join("");

}


// =========================================================
// ADD BANNED WORD
// =========================================================

async function addBannedWord() {

    const input =
        document.getElementById(
            "bannedWordInput"
        );

    if (!input) return;


    const word =
        input.value.trim();


    if (!word) {

        showMessage(
            "금지어를 입력해주세요."
        );

        input.focus();

        return;

    }


    try {

        const response =
            await fetch(
                `${API_URL}/admin/banned-words`,
                {
                    method: "POST",
                    headers: getHeaders(),
                    body: JSON.stringify({
                        word: word
                    })
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "금지어 등록에 실패했습니다."
            );

        }


        input.value =
            "";


        const deletedCount =
            Number(
                data.deleted_articles || 0
            );


        if (
            deletedCount > 0
        ) {

            showMessage(
                `"${word}" 등록 완료 — ${deletedCount}개의 기존 기사가 자동 삭제되었습니다.`
            );

        }
        else {

            showMessage(
                data.message ||
                `"${word}" 금지어가 등록되었습니다.`
            );

        }


        await loadBannedWords();

        await loadArticles();

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "금지어 등록 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// DELETE BANNED WORD
// =========================================================

async function deleteBannedWord(
    wordId,
    word
) {

    if (
        !confirm(
            `"${word}" 금지어를 삭제하시겠습니까?\n\n삭제해도 이미 삭제된 기사는 복구되지 않습니다.`
        )
    ) {

        return;

    }


    try {

        const response =
            await fetch(
                `${API_URL}/admin/banned-words/${wordId}`,
                {
                    method: "DELETE",
                    headers: getHeaders()
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "금지어 삭제에 실패했습니다."
            );

        }


        showMessage(
            data.message ||
            "금지어가 삭제되었습니다."
        );


        await loadBannedWords();

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "금지어 삭제 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// BANNED WORD ENTER KEY
// =========================================================

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const input =
            document.getElementById(
                "bannedWordInput"
            );

        if (!input) return;


        input.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Enter"
                ) {

                    event.preventDefault();

                    addBannedWord();

                }

            }
        );

    }
);


// =========================================================
// ARTICLES
// =========================================================

async function loadArticles() {

    try {

        const response =
            await fetch(
                `${API_URL}/admin/articles`,
                {
                    method: "GET",
                    headers: getHeaders()
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "기사 목록을 불러오지 못했습니다."
            );

        }


        renderArticles(
            data
        );

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "기사 목록을 불러오는 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// RENDER ARTICLES
// =========================================================

function renderArticles(
    articles
) {

    const articleList =
        document.getElementById(
            "articleList"
        );


    if (!articleList) return;


    if (!articles.length) {

        articleList.innerHTML =
            "<p class='empty'>등록된 기사가 없습니다.</p>";

        return;

    }


    articleList.innerHTML =
        articles
            .map(
                article =>
                    renderArticle(
                        article
                    )
            )
            .join("");

}


// =========================================================
// RENDER ARTICLE
// =========================================================

function renderArticle(
    article
) {

    return `

        <div class="article-row">

            <div class="article-info">

                <div class="article-title">

                    ${escapeHtml(
                        article.title
                    )}

                </div>


                ${
                    article.subtitle
                        ? `
                            <div class="article-meta">

                                ${escapeHtml(
                                    article.subtitle
                                )}

                            </div>
                          `
                        : ""
                }


                <div class="article-meta">

                    작성자:

                    ${escapeHtml(
                        article.author ||
                        "알 수 없음"
                    )}

                    &nbsp; | &nbsp;

                    ID:

                    ${article.id}

                </div>

            </div>


            <button
                class="delete"
                onclick="
                    deleteArticle(
                        ${article.id}
                    )
                "
            >
                기사 삭제
            </button>

        </div>

    `;

}


// =========================================================
// DELETE ARTICLE
// =========================================================

async function deleteArticle(
    articleId
) {

    if (
        !confirm(
            "정말 이 기사를 삭제하시겠습니까?"
        )
    ) {

        return;

    }


    try {

        const response =
            await fetch(
                `${API_URL}/admin/articles/${articleId}`,
                {
                    method: "DELETE",
                    headers: getHeaders()
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "기사 삭제에 실패했습니다."
            );

        }


        showMessage(
            data.message ||
            "기사가 삭제되었습니다."
        );


        await loadArticles();

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "기사 삭제 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// DELETE ALL ARTICLES
// =========================================================

async function deleteAllArticles() {

    if (
        !confirm(
            "⚠️ 정말 모든 뉴스를 삭제하시겠습니까?\n\n삭제한 뉴스는 복구할 수 없습니다."
        )
    ) {

        return;

    }


    if (
        !confirm(
            "마지막 확인입니다.\n\n모든 뉴스를 전부 삭제합니다."
        )
    ) {

        return;

    }


    try {

        const response =
            await fetch(
                `${API_URL}/admin/articles`,
                {
                    method: "DELETE",
                    headers: getHeaders()
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "전체 뉴스 삭제에 실패했습니다."
            );

        }


        showMessage(
            data.message ||
            "모든 뉴스가 삭제되었습니다."
        );


        await loadArticles();

    }
    catch (error) {

        console.error(
            error
        );

        showMessage(
            error.message ||
            "전체 뉴스 삭제 중 오류가 발생했습니다."
        );

    }

}


// =========================================================
// HTML ESCAPE
// =========================================================

function escapeHtml(
    value
) {

    if (
        value === null ||
        value === undefined
    ) {

        return "";

    }


    return String(value)

        .replace(
            /&/g,
            "&amp;"
        )

        .replace(
            /</g,
            "&lt;"
        )

        .replace(
            />/g,
            "&gt;"
        )

        .replace(
            /"/g,
            "&quot;"
        )

        .replace(
            /'/g,
            "&#039;"
        );

}


// =========================================================
// JAVASCRIPT STRING ESCAPE
// =========================================================

function escapeJs(
    value
) {

    if (
        value === null ||
        value === undefined
    ) {

        return "";

    }


    return String(value)
        .replace(
            /\\/g,
            "\\\\"
        )
        .replace(
            /'/g,
            "\\'"
        )
        .replace(
            /"/g,
            '\\"'
        )
        .replace(
            /\r/g,
            "\\r"
        )
        .replace(
            /\n/g,
            "\\n"
        );

}
