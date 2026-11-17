/* Paddle's checkout, opened on /plans alone (design.md §12, "/plans alone loads Paddle's
   checkout script", 2026-11-17; targum-internal#59 phase 2).

   The page carries this only in the one view our server sends after a pay press: the
   transaction it made for this account, the client-side token and the environment, on
   #paddle-checkout. Paddle.js (loaded just before, from Paddle's CDN) opens its overlay
   on that transaction; the transaction is never made here, and nothing here is priced.
   Where Paddle.js did not load, the page says the checkout did not open, as it does when
   our server could not make one. When the overlay finishes, Paddle sends the reader back
   to /plans, and the webhook is what puts the plan or the credits on the account. */
(function () {
  "use strict";
  var held = document.getElementById("paddle-checkout");
  if (!held) return;
  var transaction = held.getAttribute("data-transaction") || "";
  var token = held.getAttribute("data-token") || "";
  var sandbox = held.getAttribute("data-environment") === "sandbox";

  function failed() {
    var line = document.createElement("p");
    line.className = "fault-fact plans-checkout-failed";
    line.setAttribute("role", "status");
    line.textContent = held.getAttribute("data-failed") || "";
    var pay = document.querySelector(".plan-pay");
    (pay || document.querySelector("main") || document.body).appendChild(line);
  }

  function open() {
    var paddle = window.Paddle;
    if (!paddle || !transaction || !token) return failed();
    try {
      if (sandbox && paddle.Environment) paddle.Environment.set("sandbox");
      paddle.Initialize({ token: token });
      paddle.Checkout.open({
        transactionId: transaction,
        settings: {
          displayMode: "overlay",
          successUrl: location.origin + "/plans",
        },
      });
    } catch (error) {
      failed();
    }
    // The address keeps no transaction once it is open: a reload or a shared link
    // shows the plain page and opens nothing.
    try {
      history.replaceState(null, "", location.pathname);
    } catch (error) {}
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", open);
  else open();
})();
