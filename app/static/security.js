const statusEl = document.getElementById("status");

function setStatus(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.className = isError ? "error" : "success";
}

function b64urlToBuffer(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from(raw, c => c.charCodeAt(0)).buffer;
}

function bufferToB64url(value) {
  if (value === null || value === undefined) return null;
  const bytes = new Uint8Array(value);
  let binary = "";
  bytes.forEach(byte => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function creationOptions(options) {
  options.challenge = b64urlToBuffer(options.challenge);
  options.user.id = b64urlToBuffer(options.user.id);
  if (options.excludeCredentials) {
    options.excludeCredentials = options.excludeCredentials.map(item => ({
      ...item,
      id: b64urlToBuffer(item.id),
    }));
  }
  return options;
}

function requestOptions(options) {
  options.challenge = b64urlToBuffer(options.challenge);
  if (options.allowCredentials) {
    options.allowCredentials = options.allowCredentials.map(item => ({
      ...item,
      id: b64urlToBuffer(item.id),
    }));
  }
  return options;
}

function credentialToJSON(credential) {
  const response = {
    clientDataJSON: bufferToB64url(credential.response.clientDataJSON),
  };

  if ("attestationObject" in credential.response) {
    response.attestationObject = bufferToB64url(credential.response.attestationObject);
    if (typeof credential.response.getTransports === "function") {
      response.transports = credential.response.getTransports();
    }
  }

  if ("authenticatorData" in credential.response) {
    response.authenticatorData = bufferToB64url(credential.response.authenticatorData);
    response.signature = bufferToB64url(credential.response.signature);
    response.userHandle = bufferToB64url(credential.response.userHandle);
  }

  return {
    id: credential.id,
    rawId: bufferToB64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment || null,
    response,
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || "요청이 거부되었습니다.");
  }
  return body;
}

async function registerSecurityKey(bootstrapToken = "") {
  if (!window.PublicKeyCredential) {
    throw new Error("이 브라우저는 WebAuthn 보안키 인증을 지원하지 않습니다.");
  }

  const headers = { "Content-Type": "application/json" };
  if (bootstrapToken) headers["X-Bootstrap-Token"] = bootstrapToken;

  const options = await jsonFetch("/api/security/register/options", {
    method: "POST",
    headers,
    body: "{}",
  });

  const credential = await navigator.credentials.create({
    publicKey: creationOptions(options),
  });

  await jsonFetch("/api/security/register/verify", {
    method: "POST",
    headers,
    body: JSON.stringify(credentialToJSON(credential)),
  });
}

async function authenticateSecurityKey() {
  if (!window.PublicKeyCredential) {
    throw new Error("이 브라우저는 WebAuthn 보안키 인증을 지원하지 않습니다.");
  }

  const options = await jsonFetch("/api/security/authenticate/options", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });

  const credential = await navigator.credentials.get({
    publicKey: requestOptions(options),
  });

  await jsonFetch("/api/security/authenticate/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentialToJSON(credential)),
  });
}

document.getElementById("register-key")?.addEventListener("click", async () => {
  const token = document.getElementById("bootstrap-token")?.value || "";
  try {
    setStatus("보안키 등록을 시작합니다.");
    await registerSecurityKey(token);
    window.location.reload();
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("login-key")?.addEventListener("click", async () => {
  try {
    setStatus("보안키 인증을 시작합니다.");
    await authenticateSecurityKey();
    window.location.reload();
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("add-key")?.addEventListener("click", async () => {
  try {
    setStatus("추가 보안키 등록을 시작합니다.");
    await registerSecurityKey();
    setStatus("백업 보안키가 등록되었습니다.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("logout")?.addEventListener("click", async () => {
  try {
    await jsonFetch("/api/security/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    window.location.reload();
  } catch (error) {
    setStatus(error.message, true);
  }
});


function privateKindLabel(kind) {
  return {
    reservation: "예매/예약 번호",
    phone: "전화번호",
    email: "이메일",
    contact: "기타 연락처",
    other: "기타 민감정보",
  }[kind] || kind;
}

async function loadPrivateValues() {
  const container = document.getElementById("private-values");
  if (!container) return;
  container.textContent = "불러오는 중...";
  try {
    const body = await jsonFetch("/api/private-values");
    container.replaceChildren();
    if (!body.values.length) {
      const empty = document.createElement("p");
      empty.className = "vault-note";
      empty.textContent = "저장된 개인정보가 없습니다.";
      container.appendChild(empty);
      return;
    }
    body.values.forEach(item => {
      const row = document.createElement("div");
      row.className = "private-value-row";
      const text = document.createElement("div");
      text.className = "private-value-text";
      const label = document.createElement("strong");
      label.textContent = item.label;
      const meta = document.createElement("span");
      meta.className = "private-value-meta";
      meta.textContent = `${privateKindLabel(item.kind)} · ${item.masked_value}`;
      text.append(label, meta);

      const actions = document.createElement("div");
      actions.className = "private-value-actions";
      const reveal = document.createElement("button");
      reveal.type = "button";
      reveal.className = "secondary compact";
      reveal.textContent = "보안키로 원문 보기";
      reveal.addEventListener("click", async () => {
        try {
          setStatus("개인정보 원문 열람을 위한 보안키 재인증을 시작합니다.");
          const options = await jsonFetch(`/api/private-values/${item.id}/reveal/options`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          });
          const credential = await navigator.credentials.get({ publicKey: requestOptions(options) });
          const result = await jsonFetch(`/api/private-values/${item.id}/reveal/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(credentialToJSON(credential)),
          });
          meta.textContent = `${privateKindLabel(item.kind)} · ${result.value}`;
          setStatus("원문을 15초 동안 표시합니다.");
          window.setTimeout(() => {
            meta.textContent = `${privateKindLabel(item.kind)} · ${item.masked_value}`;
          }, 15000);
        } catch (error) {
          setStatus(error.message, true);
        }
      });

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "danger compact";
      remove.textContent = "삭제";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`${item.label} 항목을 삭제할까요?`)) return;
        try {
          await jsonFetch(`/api/private-values/${item.id}`, { method: "DELETE" });
          setStatus("암호화 개인정보 항목을 삭제했습니다.");
          await loadPrivateValues();
        } catch (error) {
          setStatus(error.message, true);
        }
      });
      actions.append(reveal, remove);
      row.append(text, actions);
      container.appendChild(row);
    });
  } catch (error) {
    container.textContent = "";
    setStatus(error.message, true);
  }
}

document.getElementById("private-value-form")?.addEventListener("submit", async event => {
  event.preventDefault();
  const kind = document.getElementById("private-kind").value;
  const labelInput = document.getElementById("private-label");
  const valueInput = document.getElementById("private-value");
  try {
    await jsonFetch("/api/private-values", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, label: labelInput.value.trim(), value: valueInput.value }),
    });
    labelInput.value = "";
    valueInput.value = "";
    setStatus("민감정보를 암호화해 저장했습니다. 목록에는 마스킹 값만 표시됩니다.");
    await loadPrivateValues();
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById("refresh-private-values")?.addEventListener("click", loadPrivateValues);
if (document.getElementById("private-vault")) loadPrivateValues();
