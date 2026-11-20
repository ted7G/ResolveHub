// Closes the header's user menu (a <details> element) on Escape or a click
// outside it, the way people expect a dropdown to behave.
"use strict";
{
    const menu = document.querySelector(".rh-usermenu");
    if (menu) {
        document.addEventListener("click", (event) => {
            if (menu.open && !menu.contains(event.target)) {
                menu.open = false;
            }
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && menu.open) {
                menu.open = false;
                menu.querySelector("summary").focus();
            }
        });
    }
}
