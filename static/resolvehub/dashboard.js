// Dashboard behaviour:
// - the greeting and date follow the viewer's own clock (the server renders
//   them in UTC, which can be the wrong part of the day for the reader);
// - chart tooltips: any element with [data-tip] shows the hidden .rh-tip-src
//   inside it on hover or keyboard focus. Tooltips repeat what the chart and
//   its table already show; they never hold the only copy of a value.
"use strict";
{
    const now = new Date();
    const greeting = document.querySelector("[data-rh-greeting]");
    const today = document.querySelector("[data-rh-today]");

    if (greeting) {
        const hour = now.getHours();
        greeting.textContent = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    }
    if (today) {
        const weekday = now.toLocaleDateString("en-GB", { weekday: "long" });
        const date = now.toLocaleDateString("en-GB", { day: "numeric", month: "long" });
        today.textContent = `${weekday}, ${date}`;
    }

    const tip = document.createElement("div");
    tip.className = "rh-tip";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.append(tip);

    function place(x, y) {
        const margin = 12;
        const { width, height } = tip.getBoundingClientRect();
        let left = x + margin;
        let top = y - height - margin;
        if (left + width > window.innerWidth - margin) {
            left = x - width - margin;
        }
        if (top < margin) {
            top = y + margin;
        }
        tip.style.left = `${Math.max(margin, left)}px`;
        tip.style.top = `${top}px`;
    }

    function show(target, x, y) {
        const source = target.querySelector(".rh-tip-src");
        if (!source) {
            return;
        }
        tip.replaceChildren(...[...source.children].map((node) => node.cloneNode(true)));
        tip.hidden = false;
        place(x, y);
    }

    function hide() {
        tip.hidden = true;
    }

    document.querySelectorAll("[data-tip]").forEach((target) => {
        target.addEventListener("pointermove", (event) => show(target, event.clientX, event.clientY));
        target.addEventListener("pointerleave", hide);
        target.addEventListener("focus", () => {
            const box = target.getBoundingClientRect();
            show(target, box.left + box.width / 2, box.top);
        });
        target.addEventListener("blur", hide);
    });
    window.addEventListener("scroll", hide, { passive: true });
}
