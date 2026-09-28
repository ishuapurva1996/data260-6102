import React, { useState } from "react";
import {
  ErrorNotice,
  FormActions,
  TitleFields,
  useSubmission,
} from "../components/forms.jsx";

export default function CreateRecord({ onAdd }) {
  const [values, setValues] = useState({
    listingTitle: "",
    propertyAddress: "",
    submitterEmail: "",
    description: "",
    propertyType: "apartment",
    termsAccepted: false,
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
    if (!values.listingTitle.trim() || !values.propertyAddress.trim())
      throw new Error("Listing title and property address cannot be blank.");
    return onAdd({
      ...values,
      listingTitle: values.listingTitle.trim(),
      propertyAddress: values.propertyAddress.trim(),
      submitterEmail: values.submitterEmail.trim(),
    });
  }, "Listing added.");
  return (
    <section className="panel form-panel">
      <p className="eyebrow">NEW RENTAL</p>
      <h1>Add a rental listing</h1>
      <p>
        Share the details that help someone find their next home. All fields are
        required.
      </p>
      <form onSubmit={submit}>
        <fieldset disabled={pending}>
          <TitleFields values={values} onChange={change} />
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
        <FormActions pending={pending} label="Add listing" />
      </form>
    </section>
  );
}
