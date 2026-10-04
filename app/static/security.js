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
