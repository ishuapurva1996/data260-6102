"use strict";

const rentalForm = document.getElementById("rentalForm");
const updateForm = document.getElementById("updateForm");
const searchForm = document.getElementById("searchForm");
const submitButton = document.getElementById("submitButton");
const updateButton = document.getElementById("updateButton");
const cancelEditButton = document.getElementById("cancelEditButton");
const updateHeading = document.getElementById("updateHeading");
const formStatus = document.getElementById("formStatus");
const updateStatus = document.getElementById("updateStatus");
const listStatus = document.getElementById("listStatus");
const rentalList = document.getElementById("rentalList");
const emptyState = document.getElementById("emptyState");
const searchQuery = document.getElementById("searchQuery");
const clearSearchButton = document.getElementById("clearSearchButton");
const deleteHighestButton = document.getElementById("deleteHighestButton");
const retryButton = document.getElementById("retryButton");
const storeSummary = document.getElementById("storeSummary");
const searchSummary = document.getElementById("searchSummary");
const updateAvailability = document.getElementById("updateAvailability");
const pageParameters = new URLSearchParams(window.location.search);

let allRentals = [];
let storeKnown = false;
let listBusy = false;
let mutationBusy = false;
let loadVersion = 0;
let loadController;
let editingRental = null;

const showStatus = (element, message, type) => {
    element.textContent = message;
    element.className = `status-message status-${type}`;
    element.setAttribute("role", type === "error" ? "alert" : "status");
    element.hidden = false;
};

const clearStatus = (element) => {
    element.textContent = "";
    element.hidden = true;
    element.setAttribute("role", "status");
};

const errorMessage = (error) => error instanceof TypeError
    ? "Could not reach the server. Check that the app is running, then try again."
    : error.message || "The request failed. Please try again.";

const requestJSON = async (url, options = {}) => {
    const response = await fetch(url, {
        ...options,
        headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) }
    });
    if (response.status === 204 && response.ok) return null;

    let data;
    try {
        data = await response.json();
    } catch {
        throw new Error(response.ok
            ? "The server returned an unreadable response. Please try again."
            : `Request failed (HTTP ${response.status}). Please try again.`);
    }
    if (!response.ok) {
        const detail = data.detail;
        const message = Array.isArray(detail)
            ? detail.map((item) => {
                const field = (item.loc || []).filter((part) => part !== "body").join(".");
                return `${field ? `${field}: ` : ""}${item.msg || "Invalid value"}`;
            }).join("; ")
            : typeof detail === "string" ? detail : "";
        throw new Error(message || `Request failed (HTTP ${response.status}). Please try again.`);
    }
    return data;
};

const updateControls = () => {
    for (const form of [rentalForm, updateForm, searchForm]) {
        for (const control of form.elements) control.disabled = mutationBusy;
    }
    submitButton.disabled = mutationBusy || listBusy;
    const selectedExists = editingRental && allRentals.some((rental) => rental.id === editingRental.id);
    updateButton.disabled = mutationBusy || listBusy || !storeKnown || !selectedExists;
    updateAvailability.hidden = !editingRental || (storeKnown && selectedExists);
    updateAvailability.textContent = !storeKnown
        ? "Reload listings to check whether this listing is still available."
        : "This listing is no longer available. Cancel editing and choose another listing.";
    deleteHighestButton.disabled = mutationBusy || listBusy || !storeKnown || allRentals.length === 0;
    retryButton.disabled = mutationBusy || listBusy;
    for (const button of rentalList.querySelectorAll("button")) {
        button.disabled = mutationBusy || listBusy || !storeKnown;
    }
    rentalForm.setAttribute("aria-busy", String(mutationBusy));
    updateForm.setAttribute("aria-busy", String(mutationBusy));
    searchForm.setAttribute("aria-busy", String(listBusy));
    rentalList.setAttribute("aria-busy", String(listBusy));
};

const renderStoreSummary = () => {
    const highest = allRentals.length ? Math.max(...allRentals.map((rental) => rental.id)) : null;
    storeSummary.textContent = `${allRentals.length} listing${allRentals.length === 1 ? "" : "s"} total.`
        + (highest === null ? "" : ` Highest ID: ${highest}.`);
    deleteHighestButton.textContent = highest === null
        ? "Delete highest-ID listing"
        : `Delete highest-ID listing (${highest})`;
};

const beginEdit = (rental) => {
    if (mutationBusy || listBusy || !storeKnown) return;
    if (editingRental?.id !== rental.id) {
        const hasChanges = editingRental && (
            updateForm.elements.listingTitle.value !== editingRental.listingTitle
            || updateForm.elements.propertyAddress.value !== editingRental.propertyAddress
        );
        if (hasChanges && !window.confirm("Discard unsaved changes and edit another listing?")) return;
        editingRental = rental;
        updateForm.elements.listingTitle.value = rental.listingTitle;
        updateForm.elements.propertyAddress.value = rental.propertyAddress;
        updateHeading.textContent = `Edit Listing ID ${rental.id}`;
        clearStatus(updateStatus);
    }
    updateForm.hidden = false;
    updateControls();
    updateForm.scrollIntoView({ block: "start" });
    updateForm.elements.listingTitle.focus({ preventScroll: true });
};

const renderRentals = (rentals, query) => {
    rentalList.replaceChildren();
    for (const rental of rentals) {
        const row = document.createElement("li");
        row.id = `rental-${rental.id}`;
        row.dataset.id = String(rental.id);
        const heading = document.createElement("h3");
        heading.textContent = `Listing ID ${rental.id}: ${rental.listingTitle}`;
        row.appendChild(heading);
        for (const [label, value] of [
            ["Address", rental.propertyAddress], ["Email", rental.submitterEmail],
            ["Property Type", rental.propertyType], ["Description", rental.description]
        ]) {
            const line = document.createElement("p");
            line.textContent = `${label}: ${value}`;
            row.appendChild(line);
        }
        const actions = document.createElement("div");
        actions.className = "action-group";
        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "secondary-button";
        editButton.textContent = "Edit";
        editButton.dataset.editId = String(rental.id);
        editButton.setAttribute("aria-label", `Edit listing ID ${rental.id}`);
        editButton.addEventListener("click", () => beginEdit(rental));
        actions.appendChild(editButton);
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Delete";
        button.setAttribute("aria-label", `Delete listing ID ${rental.id}`);
        button.addEventListener("click", () => {
            if (mutationBusy || listBusy) return;
            if (!window.confirm(`Delete listing ID ${rental.id}: ${rental.listingTitle}?`)) return;
            performMutation(listStatus, "Deleting rental listing...", () => requestJSON(`/api/rentals/${rental.id}`, { method: "DELETE" }));
        });
        actions.appendChild(button);
        row.appendChild(actions);
        rentalList.appendChild(row);
    }
    rentalList.hidden = rentals.length === 0;
    emptyState.hidden = rentals.length > 0;
    emptyState.textContent = allRentals.length === 0
        ? "No rental listings yet. Create your first listing above."
        : "No matching listings. Try another title or address, or clear the search.";
    searchSummary.textContent = query
        ? `${rentals.length} match${rentals.length === 1 ? "" : "es"} for “${query}”.`
        : `Showing all ${rentals.length} listing${rentals.length === 1 ? "" : "s"}.`;
};

const loadRentals = async () => {
    if (mutationBusy) return;
    const version = ++loadVersion;
    loadController?.abort();
    loadController = new AbortController();
    const signal = loadController.signal;
    const query = searchQuery.value.trim();
    listBusy = true;
    retryButton.hidden = true;
    showStatus(listStatus, query ? "Searching rental listings..." : "Loading rental listings...", "loading");
    updateControls();
    try {
        // The global deletion control always uses the unfiltered collection.
        const [all, filtered] = await Promise.all([
            requestJSON("/api/rentals", { signal }),
            query ? requestJSON(`/api/rentals?q=${encodeURIComponent(query)}`, { signal }) : Promise.resolve(null)
        ]);
        if (version !== loadVersion) return;
        allRentals = all;
        storeKnown = true;
        renderStoreSummary();
        renderRentals(filtered || all, query);
        clearStatus(listStatus);
    } catch (error) {
        if (version !== loadVersion || error.name === "AbortError") return;
        storeKnown = false;
        showStatus(listStatus, errorMessage(error), "error");
        retryButton.hidden = false;
        storeSummary.textContent = "Listing count unavailable until loading succeeds.";
    } finally {
        if (version === loadVersion) {
            listBusy = false;
            updateControls();
        }
    }
};

const validateForm = (form, status) => {
    for (const control of form.elements) {
        if (!control.required) continue;
        let message = "";
        if (control.type === "checkbox") {
            if (!control.checked) message = "Please agree to the terms and conditions.";
        } else if (!control.value.trim()) {
            message = "Please complete all required fields.";
        } else if (control.type === "email" && !control.validity.valid) {
            message = "Enter a valid landlord email address.";
        } else if (control.id === "description" && [...control.value.trim()].length < 26) {
            message = "Description must contain more than 25 characters.";
        }
        if (message) {
            showStatus(status, message, "error");
            control.focus();
            return false;
        }
    }
    return true;
};

const performMutation = async (status, message, operation) => {
    if (mutationBusy || listBusy) return;
    mutationBusy = true;
    showStatus(status, message, "loading");
    updateControls();
    try {
        await operation();
        // A full home navigation reloads the authoritative server state.
        window.location.assign("/");
    } catch (error) {
        showStatus(status, errorMessage(error), "error");
        mutationBusy = false;
        updateControls();
    }
};

rentalForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (mutationBusy || listBusy) return;
    clearStatus(formStatus);
    if (!validateForm(rentalForm, formStatus)) return;
    const fields = rentalForm.elements;
    const payload = {
        listingTitle: fields.listingTitle.value.trim(),
        propertyAddress: fields.propertyAddress.value.trim(),
        submitterEmail: fields.submitterEmail.value.trim(),
        description: fields.description.value.trim(),
        propertyType: fields.propertyType.value,
        termsAccepted: fields.termsAccepted.checked
    };
    performMutation(formStatus, "Saving your rental listing...", async () => {
        // Explicit screenshot aids: ordinary saves have no artificial delay.
        const simulateError = pageParameters.get("simulateError") === "true";
        const delay = pageParameters.get("slowSave") === "true" ? 8000 : simulateError ? 2000 : 0;
        if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
        if (simulateError) throw new Error("The rental listing could not be saved. Please try again.");
        await requestJSON("/api/rentals", { method: "POST", body: JSON.stringify(payload) });
    });
});

updateForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (updateButton.disabled) return;
    clearStatus(updateStatus);
    if (!validateForm(updateForm, updateStatus)) return;
    const payload = {
        listingTitle: updateForm.elements.listingTitle.value.trim(),
        propertyAddress: updateForm.elements.propertyAddress.value.trim()
    };
    const rentalId = editingRental.id;
    performMutation(updateStatus, `Updating listing ID ${rentalId}...`, () => requestJSON(`/api/rentals/${rentalId}`, { method: "PUT", body: JSON.stringify(payload) }));
});

cancelEditButton.addEventListener("click", () => {
    if (mutationBusy || !editingRental) return;
    const editButton = rentalList.querySelector(`[data-edit-id="${editingRental.id}"]`);
    editingRental = null;
    updateForm.reset();
    updateForm.hidden = true;
    clearStatus(updateStatus);
    updateControls();
    (editButton && !editButton.disabled ? editButton : searchQuery).focus();
});

searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    loadRentals();
});
clearSearchButton.addEventListener("click", () => {
    searchQuery.value = "";
    loadRentals();
});
retryButton.addEventListener("click", loadRentals);
deleteHighestButton.addEventListener("click", () => {
    if (deleteHighestButton.disabled) return;
    const highest = Math.max(...allRentals.map((rental) => rental.id));
    if (!window.confirm(`Delete the highest-ID listing from all listings, including those hidden by search? Last loaded highest ID: ${highest}.`)) return;
    performMutation(listStatus, "Deleting the highest-ID listing...", () => requestJSON("/api/rentals/highest", { method: "DELETE" }));
});

for (const [form, status] of [[rentalForm, formStatus], [updateForm, updateStatus]]) {
    form.addEventListener("input", () => {
        if (!mutationBusy) clearStatus(status);
    });
}
document.addEventListener("DOMContentLoaded", loadRentals);
