(() => {
  "use strict";

  // --- Menu navigasi mobile -------------------------------------------------
  const menuButton = document.querySelector("[data-menu-button]");
  const nav = document.querySelector("[data-menu]");

  if (menuButton && nav) {
    const iconOpen = menuButton.querySelector("[data-icon-open]");
    const iconClose = menuButton.querySelector("[data-icon-close]");

    const setOpen = (open) => {
      nav.classList.toggle("hidden", !open);
      nav.classList.toggle("flex", open);
      menuButton.setAttribute("aria-expanded", String(open));
      menuButton.setAttribute("aria-label", open ? "Tutup menu" : "Buka menu");
      iconOpen?.classList.toggle("hidden", open);
      iconClose?.classList.toggle("hidden", !open);
    };

    menuButton.addEventListener("click", () => {
      setOpen(menuButton.getAttribute("aria-expanded") !== "true");
    });

    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setOpen(false));
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
        setOpen(false);
        menuButton.focus();
      }
    });
  }

  // --- Animasi reveal (Motion) ----------------------------------------------
  const revealItems = document.querySelectorAll("[data-reveal]");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const showAll = () => revealItems.forEach((el) => el.classList.add("is-revealed"));

  if (reduceMotion || !window.Motion) {
    showAll();
    return;
  }

  const { animate, inView } = window.Motion;

  revealItems.forEach((el) => {
    inView(
      el,
      () => {
        el.classList.add("is-revealed");
        animate(
          el,
          { opacity: [0, 1], y: [22, 0] },
          { duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: Number(el.dataset.revealDelay || 0) }
        );
      },
      { amount: 0.12 }
    );
  });
})();
