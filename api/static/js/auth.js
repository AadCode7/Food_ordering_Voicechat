(() => {
  if (getToken()) { location.href = "/dashboard"; return; }
  const $ = (id) => document.getElementById(id);
  let mode = "in";
  function setMode(m) {
    mode = m;
    $("tab-in").classList.toggle("active", m === "in");
    $("tab-up").classList.toggle("active", m === "up");
    $("name-wrap").hidden = m === "in";
    $("name").required = m === "up";
    $("password").autocomplete = m === "in" ? "current-password" : "new-password";
    $("submit").textContent = m === "in" ? "Sign in" : "Create account";
    $("err").textContent = "";
  }
  $("tab-in").onclick = () => setMode("in");
  $("tab-up").onclick = () => setMode("up");
  $("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("err").textContent = "";
    $("submit").disabled = true;
    try {
      const payload = { email: $("email").value, password: $("password").value };
      if (mode === "up") payload.name = $("name").value;
      const data = await apiFetch(mode === "in" ? "/auth/signin" : "/auth/signup", { method: "POST", body: payload, auth: false });
      setToken(data.access_token);
      location.href = "/dashboard";
    } catch (err) {
      $("err").textContent = err.message;
    } finally {
      $("submit").disabled = false;
    }
  });
})();
