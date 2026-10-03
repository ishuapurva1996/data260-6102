import React, { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { createRental } from "../features/rentals/rentalsSlice.js";
import {
  ErrorNotice,
  FormActions,
  RentalFields,
  rentalFields,
  useManagers,
  useSubmission,
} from "../components/forms.jsx";

export default function CreateRecord() {
  const dispatch = useDispatch();
  const managers = useManagers();
  const saving = useSelector((state) => state.rentals.mutations.create?.status === "pending");
  const [values, setValues] = useState({
    listingTitle: "",
    propertyAddress: "",
    submitterEmail: "",
    description: "",
    propertyType: "apartment",
    termsAccepted: false,
    listingCode: "",
    availableUnits: "1",
    managerId: "",
  });
  const change = (event) =>
    setValues((previous) => ({
      ...previous,
      [event.target.name]:
        event.target.type === "checkbox"
          ? event.target.checked
          : event.target.value,
    }));
  const { pending, error, submit } = useSubmission(() => {
    const fields = rentalFields(values, true);
    return dispatch(createRental({
      ...fields,
      submitterEmail: values.submitterEmail.trim(),
      description: values.description,
      propertyType: values.propertyType,
      termsAccepted: values.termsAccepted,
    })).unwrap();
  }, "Listing added.");
  return (
    <section className="panel form-panel">
      <p className="eyebrow">NEW RENTAL</p>
      <h1>Add a rental listing</h1>
      <p>
        Share the details that help someone find their next home. All fields except the listing code are
        required.
      </p>
      <form onSubmit={submit}>
        <fieldset disabled={pending || saving}>
          <RentalFields values={values} onChange={change} managers={managers} creating />
          <label>
            Landlord Email
            <input
              name="submitterEmail"
              type="email"
              required
              autoComplete="email"
              value={values.submitterEmail}
              onChange={change}
            />
          </label>
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            name="description"
            required
            minLength={26}
            aria-describedby="description-hint"
            value={values.description}
            onChange={change}
          />
          <p className="hint" id="description-hint">
            Use at least 26 characters to describe the rental.
          </p>
          <label htmlFor="propertyType">Property type</label>
          <select
            id="propertyType"
            name="propertyType"
            value={values.propertyType}
            onChange={change}
          >
            <option value="apartment">Apartment</option>
            <option value="house">House</option>
            <option value="condo">Condo</option>
            <option value="townhouse">Townhouse</option>
          </select>
          <label className="checkbox">
            <input
              name="termsAccepted"
              type="checkbox"
              required
              checked={values.termsAccepted}
              onChange={change}
            />
            I accept the terms
          </label>
        </fieldset>
        <ErrorNotice error={error} />
        <FormActions pending={pending || saving} disabled={managers.loading || !!managers.error || !managers.records.length} label="Add listing" />
      </form>
    </section>
  );
}
