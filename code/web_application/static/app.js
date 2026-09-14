// ===== CONCEPT 1: STRICT MODE =====
"use strict";

const rentalForm = document.getElementById("rentalForm");
const submitButton = document.getElementById("submitButton");
const formStatus = document.getElementById("formStatus");
const rentalList = document.getElementById("rentalList");
const emptyState = document.getElementById("emptyState");
const listingTitleInput = document.getElementById("listingTitle");
const propertyAddressInput = document.getElementById("propertyAddress");
const submitterEmailInput = document.getElementById("submitterEmail");
const descriptionInput = document.getElementById("description");
const propertyTypeInput = document.getElementById("propertyType");
const termsAcceptedInput = document.getElementById("termsAccepted");
const editableControls = [
    listingTitleInput,
    propertyAddressInput,
    submitterEmailInput,
    descriptionInput,
    propertyTypeInput,
    termsAcceptedInput
];
const pageParameters = new URLSearchParams(window.location.search);
const shouldSimulateSaveError = pageParameters.get("simulateError") === "true";
const saveDelayMs = pageParameters.get("slowSave") === "true" ? 8000 : 2000;
const defaultSubmitText = submitButton.textContent;
let isSubmitting = false;

const showFormStatus = (message, type) => {
    formStatus.textContent = message;
    formStatus.className = `status-message status-${type}`;
    formStatus.setAttribute("role", type === "error" ? "alert" : "status");
    formStatus.hidden = false;
};

const clearFormStatus = () => {
    formStatus.textContent = "";
    formStatus.className = "status-message";
    formStatus.setAttribute("role", "status");
    formStatus.hidden = true;
};

const updateEmptyState = () => {
    const hasListings = rentalList.children.length > 0;
    emptyState.hidden = hasListings;
    rentalList.hidden = !hasListings;
};

const setSubmittingState = (submitting) => {
    isSubmitting = submitting;
    editableControls.forEach((control) => {
        control.disabled = submitting;
    });
    submitButton.disabled = submitting;
    submitButton.textContent = submitting ? "Saving..." : defaultSubmitText;
    rentalForm.setAttribute("aria-busy", String(submitting));
};

// ===== CONCEPT 2: FORM VALIDATION =====
const validateForm = () => {
    const requiredInputs = [listingTitleInput, propertyAddressInput, submitterEmailInput, descriptionInput];
    const firstEmptyInput = requiredInputs.find((input) => !input.value.trim());

    if (firstEmptyInput) {
        showFormStatus("Please complete all required fields.", "error");
        firstEmptyInput.focus();
        return false;
    }

    if (!submitterEmailInput.validity.valid) {
        showFormStatus("Enter a valid landlord email address.", "error");
        submitterEmailInput.focus();
        return false;
    }

    const description = descriptionInput.value.trim();
    if (description.length <= 25) {
        showFormStatus("Description must contain more than 25 characters.", "error");
        descriptionInput.focus();
        return false;
    }

    if (!propertyTypeInput.value) {
        showFormStatus("Choose a property type.", "error");
        propertyTypeInput.focus();
        return false;
    }

    if (!termsAcceptedInput.checked) {
        showFormStatus("Please agree to the terms and conditions.", "error");
        termsAcceptedInput.focus();
        return false;
    }

    return true;
};

// ===== CONCEPT 3: CLOSURES =====
const submissionCounter = (() => {
    let count = 0;
    return () => ++count;
})();

// ===== CONCEPT 4: PROMISES AND ASYNC/AWAIT =====
// The query parameters make the required loading and error states easy to demonstrate in screenshots.
const saveRentalToServer = (rentalData) => {
    return new Promise((resolve, reject) => {
        console.log("Saving rental listing to server...");

        setTimeout(() => {
            if (shouldSimulateSaveError) {
                reject(new Error("The rental listing could not be saved. Please try again."));
                return;
            }

            resolve(`Rental listing "${rentalData.listingTitle}" saved successfully!`);
        }, saveDelayMs);
    });
};

// ===== CONCEPT 5: EVENT LISTENERS =====
rentalForm.addEventListener("input", () => {
    if (!isSubmitting && !formStatus.hidden) {
        clearFormStatus();
    }
});

rentalForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (isSubmitting) return;

    clearFormStatus();
    if (!validateForm()) return;

    setSubmittingState(true);
    showFormStatus("Saving your rental listing...", "loading");

    const listingTitle = listingTitleInput.value.trim();
    const propertyAddress = propertyAddressInput.value.trim();
    const submitterEmail = submitterEmailInput.value.trim();
    const description = descriptionInput.value.trim();
    const propertyType = propertyTypeInput.value;
    const termsAccepted = termsAcceptedInput.checked;

    const rentalData = {listingTitle, propertyAddress, submitterEmail, description, propertyType, termsAccepted};

    const jsonRentalData = JSON.stringify(rentalData);
    console.log("Rental Data (String):", jsonRentalData);

    const parsedRentalData = JSON.parse(jsonRentalData);
    console.log("Rental Data (JSON):", parsedRentalData);

    const {listingTitle: rentalListingTitle, submitterEmail: rentalSubmitterEmail} = parsedRentalData;
    console.log("Listing Title:", rentalListingTitle);
    console.log("Submitter Email:", rentalSubmitterEmail);

    const currentCount = submissionCounter();
    const updatedRentalData = {
        ...parsedRentalData,
        submissionDate: new Date().toISOString(),
        id: `rental-${currentCount}`
    };
    console.log("Submission Counter:", currentCount);
    console.log("Updated Rental Data:", updatedRentalData);

    try {
        const serverResponse = await saveRentalToServer(updatedRentalData);
        console.log(serverResponse);

        addRentalToUI(updatedRentalData);
        rentalForm.reset();
        showFormStatus("Rental listing saved successfully.", "success");
    } catch (error) {
        console.error(error);
        showFormStatus(error.message || "The rental listing could not be saved. Please try again.", "error");
    } finally {
        setSubmittingState(false);
    }
});

// ===== HELPER FUNCTION FOR UI =====
const addRentalToUI = (rentalData) => {
    const {listingTitle, propertyAddress, submitterEmail, propertyType, id} = rentalData;
    const listItem = document.createElement("li");
    listItem.id = id;
    listItem.textContent = `Listing: ${listingTitle} | Address: ${propertyAddress} | Email: ${submitterEmail} | Property Type: ${propertyType}`;

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.textContent = "Delete";
    deleteButton.setAttribute("aria-label", `Delete ${listingTitle}`);
    deleteButton.onclick = handleDelete.bind(null, listItem);

    listItem.appendChild(deleteButton);
    rentalList.appendChild(listItem);
    updateEmptyState();
};

// ===== CALL, APPLY, AND BIND FOR RENTAL DELETION =====
const handleDelete = function (rentalElement) {
    console.log(`Deleting rental listing: ${rentalElement.id}`);
    rentalElement.remove();
    updateEmptyState();
};

updateEmptyState();
