// Small admin enhancements, loaded with the help desk pages:
// - long dropdowns become searchable, using the Select2 copy that ships with
//   Django's admin (the widget its autocomplete fields already use);
// - long filter lists in the sidebar get a search box.
// Both only change how options are picked; the options themselves still come
// from the server, so permission rules on what may be chosen are unchanged.
"use strict";
{
    const $ = django.jQuery;
    const MIN_OPTIONS = 8;
    const MIN_FILTER_ITEMS = 9;
    const SKIP = [
        'select[name="action"]',
        "select[multiple]",
        "select:disabled",
        ".admin-autocomplete",
        ".empty-form select",
        "#changelist-search select",
    ].join(", ");

    function makeSearchable(root) {
        $(root).find("select").not(SKIP).each(function () {
            if (this.options.length < MIN_OPTIONS || $(this).data("select2")) {
                return;
            }
            $(this).select2({
                theme: "admin-autocomplete",
                width: "resolve",
                dropdownAutoWidth: true,
            });
            // Select2 announces the selected value; give it the field's name too.
            const label = (this.id && document.querySelector(`label[for="${CSS.escape(this.id)}"]`))
                || this.closest("label");
            if (label) {
                const name = label.firstChild && label.firstChild.nodeType === Node.TEXT_NODE
                    ? label.firstChild.textContent
                    : label.textContent;
                $(this).next(".select2-container").find(".select2-selection")
                    .attr("aria-label", name.replace(/:\s*$/, "").trim());
            }
        });
    }

    function addFilterSearch() {
        document.querySelectorAll("#changelist-filter details").forEach((group) => {
            const list = group.querySelector("ul");
            const items = group.querySelectorAll("li");
            if (!list || items.length < MIN_FILTER_ITEMS) {
                return;
            }
            const title = group.dataset.filterTitle || "options";
            const input = document.createElement("input");
            input.type = "search";
            input.className = "rh-filter-search";
            input.placeholder = `Search ${title}`;
            input.setAttribute("aria-label", `Search ${title}`);
            const empty = document.createElement("p");
            empty.className = "rh-filter-empty";
            empty.textContent = "No matches";
            empty.hidden = true;
            list.before(input);
            list.after(empty);

            input.addEventListener("input", () => {
                const query = input.value.trim().toLowerCase();
                let shown = 0;
                items.forEach((item) => {
                    const match = !query || item.textContent.toLowerCase().includes(query);
                    item.hidden = !match;
                    shown += match ? 1 : 0;
                });
                empty.hidden = shown > 0;
            });
        });
    }

    $(function () {
        makeSearchable(document);
        addFilterSearch();
    });

    // Rows added with "Add another" get the same treatment.
    document.addEventListener("formset:added", (event) => makeSearchable(event.target));
}
