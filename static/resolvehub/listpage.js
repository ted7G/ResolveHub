// List page conveniences on top of Django's changelist:
// - search runs as you type, after a short pause (Enter still works);
// - the bulk-action button only lights up once an action and at least one
//   row are chosen, and the agent picker only shows for actions that use it.
"use strict";
{
    const SEARCH_DELAY_MS = 450;
    const FOCUS_KEY = "rh.searchFocus";

    function liveSearch() {
        const form = document.getElementById("changelist-search");
        const input = document.getElementById("searchbar");
        if (!form || !input) {
            return;
        }
        form.classList.add("rh-live");
        const initial = input.value;
        let timer = null;

        input.addEventListener("input", () => {
            clearTimeout(timer);
            const value = input.value.trim();
            // One letter matches almost everything; wait for a second one.
            if (value === initial.trim() || value.length === 1) {
                return;
            }
            timer = setTimeout(() => {
                try {
                    sessionStorage.setItem(FOCUS_KEY, "1");
                } catch (error) {
                    // Private windows can refuse storage; focus just won't be restored.
                }
                form.classList.add("is-searching");
                form.requestSubmit();
            }, SEARCH_DELAY_MS);
        });

        // After a search triggered by typing, carry on where the user was.
        let restore = false;
        try {
            restore = sessionStorage.getItem(FOCUS_KEY) === "1";
            sessionStorage.removeItem(FOCUS_KEY);
        } catch (error) {
            restore = false;
        }
        if (restore) {
            input.focus();
            input.setSelectionRange(input.value.length, input.value.length);
        }
    }

    function actionBar() {
        const bar = document.querySelector("#changelist .actions");
        if (!bar) {
            return;
        }
        const action = bar.querySelector('select[name="action"]');
        const apply = bar.querySelector(".rh-apply");
        const agent = bar.querySelector('select[name="agent"]');
        const agentLabel = agent ? agent.closest("label") : null;
        if (!action || !apply) {
            return;
        }

        function selectedRows() {
            if (document.querySelector("#changelist-form input.select-across[value='1']")) {
                return true;
            }
            return document.querySelectorAll("#result_list input.action-select:checked").length > 0;
        }

        function update() {
            const needsAgent = action.value === "assign_to_agent";
            if (agentLabel) {
                agentLabel.hidden = !needsAgent;
            }
            const ready = action.value !== "" && selectedRows() && (!needsAgent || (agent && agent.value));
            apply.disabled = !ready;
            apply.classList.toggle("default", ready);
        }

        action.addEventListener("change", update);
        if (agent) {
            agent.addEventListener("change", update);
            // Select2 reports changes through jQuery.
            if (window.django && django.jQuery) {
                django.jQuery(agent).on("change", update);
            }
        }
        document.getElementById("changelist-form")?.addEventListener("change", update);
        document.addEventListener("click", (event) => {
            if (event.target.closest(".actions .question, .actions .clear")) {
                setTimeout(update, 0);
            }
        });
        update();
    }

    function start() {
        liveSearch();
        actionBar();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
}
