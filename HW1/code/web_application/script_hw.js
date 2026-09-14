// ===== CONCEPT 1: STRICT MODE =====
"use strict";


const validateForm = () => {
    const listingTitle = document.getElementById("listingTitle").value.trim();
    const propertyAddress = document.getElementById("propertyAddress").value.trim();
    const submitterEmail = document.getElementById("submitterEmail").value.trim();
    const description = document.getElementById("description").value.trim();
    const termsAccepted = document.getElementById("termsAccepted");

    if (!listingTitle || !propertyAddress || !submitterEmail || !description) {
        alert("All fields are required!");
        return false;
    }

    if (description.length <= 25) {
        alert("Description must contain more than 25 characters.");
        return false;
    }

    if (!termsAccepted.checked) {
        alert("Please agree to the terms and conditions.");
        return false;
    }

    return true;
};

// ===== CONCEPT 3: CLOSURES =====
// Closure to track total successful rental listing submissions
const submissionCounter = (() => {
    let count = 0;
    return () => ++count;
})();


// ===== CONCEPT 4: PROMISES AND ASYNC/AWAIT =====
// Simulate saving a rental listing to a server

const saveRentalToServer = (rentalData) => {
    return new Promise((resolve, reject) => {
        console.log("Saving rental listing to server...");
        setTimeout(() => {
            resolve(
                `Rental listing "${rentalData.listingTitle}" saved successfully!`);
        }, 2000);
    });
};


// ===== CONCEPT 5: EVENT LISTENERS =====
// Listen for submission of the rental form

const rentalForm = document.getElementById("rentalForm");
const submitButton = rentalForm.querySelector('button[type="submit"]');
let isSubmitting = false;

rentalForm.addEventListener("submit", async (e) => {
    // Prevent normal form submission and page reload
    e.preventDefault();

    if (isSubmitting) return;

    // ===== CONCEPT 6: FORM VALIDATION =====
    if (!validateForm()) return;

    isSubmitting = true;
    submitButton.disabled = true;


    // ===== CONCEPT 7: COLLECTING FORM DATA =====
    const listingTitle = document.getElementById("listingTitle").value.trim();
    const propertyAddress = document.getElementById("propertyAddress").value.trim();
    const submitterEmail = document.getElementById("submitterEmail").value.trim();
    const description = document.getElementById("description").value.trim();
    const propertyType = document.getElementById("propertyType").value;
    const termsAccepted = document.getElementById("termsAccepted").checked;


    // Create a rental listing object

    const rentalData = {listingTitle, propertyAddress, submitterEmail, description, propertyType,termsAccepted};

    // Convert JavaScript object into JSON string
    const jsonRentalData = JSON.stringify(rentalData);
    console.log("Rental Data (String):",jsonRentalData);

    // Convert JSON string back into JavaScript object
    const parsedRentalData = JSON.parse(jsonRentalData);
    console.log("Rental Data (JSON):",parsedRentalData);

    // Use object destructuring to extract the primary field and email field from the parsed object
    const {listingTitle: rentalListingTitle, submitterEmail: landlordEmail} = parsedRentalData;
    console.log("Listing Title:",rentalListingTitle);
    console.log("Submitter Email:",landlordEmail);

    // ===== CONCEPT 10: SPREAD OPERATOR + CLOSURE IN ACTION =====
    const currentCount = submissionCounter();
    const updatedRentalData = {...parsedRentalData, submissionDate: new Date().toISOString(), id: `rental-${currentCount}`};
    console.log("Submission Counter:",currentCount);
    console.log("Updated Rental Data:",updatedRentalData);


    // ===== CONCEPT 11: PROMISES IN ACTION =====

    try {
        const serverResponse = await saveRentalToServer(updatedRentalData);
        console.log(serverResponse);

        // Add the rental listing to UI
        addRentalToUI(updatedRentalData);
        alert("Rental listing submitted successfully!");

        // Clear the form only after a successful submission
        rentalForm.reset();
    }
    catch (error) {
        console.error(error);
        alert(error);
    }
    finally {
        isSubmitting = false;
        submitButton.disabled = false;
    }
});


// ===== HELPER FUNCTION FOR UI =====

// Add submitted rental listing to the webpage

const addRentalToUI = (rentalData) => {
    const {listingTitle, propertyAddress, submitterEmail, propertyType, id} = rentalData;
    // Create a list item
    const listItem = document.createElement("li");
    listItem.setAttribute("id",id);
    listItem.textContent = `Listing: ${listingTitle} | ` + `Address: ${propertyAddress} | ` + `Email: ${submitterEmail} | ` + `Property Type: ${propertyType}`;

    // Create delete button
    const deleteButton = document.createElement("button");
    deleteButton.textContent = "Delete";
    deleteButton.onclick = handleDelete.bind(null, id);

    // Add delete button to list item
    listItem.appendChild(deleteButton);

    // Add list item to submission list
    document.getElementById("rentalList").appendChild(listItem);
};


// ===== CALL, APPLY AND BIND FOR RENTAL DELETION =====

const handleDelete = function (id) {
    const rentalElement = document.getElementById(id);
    console.log(`Deleting rental listing: ${id}`);
    rentalElement.remove();
};
