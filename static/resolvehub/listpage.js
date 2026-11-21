// List page conveniences on top of Django's changelist:
// - search runs as you type, after a short pause (Enter still works);
// - the bulk-action button only lights up once an action and at least one
//   row are chosen, and the agent picker only shows for actions that use it.
"use strict";
{
    const SEARCH_DELAY_MS = 450;
    const FOCUS_KEY = "rh.searchFocus";
    const TYPED_KEY = "rh.searchTyped";

    // Anything on the list the user changed but hasn't submitted yet: ticked
    // rows, or edits in list-editable columns (e.g. agent availability).
    // Searching reloads the page, so it must not throw that away.
    function hasUnsavedWork() {
        const listForm = document.getElementById("changelist-form");
        if (!listForm) {
            return false;
        }
        for (const field of listForm.elements) {
            if (
                !field.name ||
                field.tagName === "BUTTON" ||
                ["hidden", "submit", "button", "reset"].includes(field.type) ||
                field.name === "action" ||
                field.name === "agent"
            ) {
                continue;
            }
            if (field.type === "checkbox" || field.type === "radio") {
                if (field.checked !== field.defaultChecked) {
                    return true;
                }
            } else if (field.tagName === "SELECT") {
                if ([...field.options].some((option) => option.selected !== option.defaultSelected)) {
                    return true;
                }
            } else if (field.value !== field.defaultValue) {
                return true;
            }
        }
        return false;
    }

    function store(key, value) {
        try {
            if (value === null) {
                sessionStorage.removeItem(key);
            } else {
                sessionStorage.setItem(key, value);
            }
        } catch (error) {
            // Private windows can refuse storage; the search still works.
        }
    }

    function read(key) {
        try {
            return sessionStorage.getItem(key);
        } catch (error) {
            return null;
        }
    }

    function liveSearch() {
        const form = document.getElementById("changelist-search");
        const input = document.getElementById("searchbar");
        if (!form || !input) {
            return;
        }
        form.classList.add("rh-live");
        const note = document.createElement("span");
        note.className = "rh-search-note";
        note.hidden = true;
        note.textContent = "You have unsaved changes on this page: press Enter to search.";
        input.after(note);

        let submitted = input.value.trim();
        let timer = null;

        function schedule() {
            clearTimeout(timer);
            const value = input.value.trim();
            // Typing during the reload still lands in this box; keep it for the next page.
            store(TYPED_KEY, input.value);
            // One letter matches almost everything; wait for a second one.
            if (value === submitted || value.length === 1) {
                return;
            }
            timer = setTimeout(() => {
                if (hasUnsavedWork()) {
                    note.hidden = false;
                    return;
                }
                note.hidden = true;
                submitted = value;
                store(FOCUS_KEY, "1");
                form.classList.add("is-searching");
                form.requestSubmit();
            }, SEARCH_DELAY_MS);
        }

        input.addEventListener("input", (event) => {
            // Wait until an input method (Japanese, Chinese...) finishes the word.
            if (!event.isComposing) {
                schedule();
            }
        });
        input.addEventListener("compositionend", schedule);

        // After a search triggered by typing, carry on where the user was,
        // including anything typed while the new page was loading.
        if (read(FOCUS_KEY) === "1") {
            store(FOCUS_KEY, null);
            const typed = read(TYPED_KEY);
            input.focus();
            if (typed !== null && typed !== input.value) {
                input.value = typed;
                schedule();
            }
            input.setSelectionRange(input.value.length, input.value.length);
        }
        store(TYPED_KEY, null);
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
