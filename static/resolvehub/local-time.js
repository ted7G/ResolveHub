// The dashboard greeting and date follow the viewer's own clock. The server
// renders them in UTC, which can be the wrong part of the day (or the wrong
// day) for the person reading them; that version stays if scripts are off.
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
}
