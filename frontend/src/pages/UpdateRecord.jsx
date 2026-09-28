import React, { useState } from "react";
import {
  ErrorNotice,
  FormActions,
  RecordState,
  TitleFields,
  useSelectedRental,
  useSubmission,
} from "../components/forms.jsx";

function UpdateForm({ record, onUpdate }) {
  const [values, setValues] = useState({
    listingTitle: record.listingTitle,
    propertyAddress: record.propertyAddress,
  });
  const { pending, error, submit } = useSubmission(() => {
    const fields = {
      listingTitle: values.listingTitle.trim(),
      propertyAddress: values.propertyAddress.trim(),
    };
    if (!fields.listingTitle || !fields.propertyAddress)
      throw new Error("Listing title and property address cannot be blank.");
    return onUpdate(record.id, fields);
  }, "Listing updated.");
  return (
    <section className="panel form-panel">
      <p className="eyebrow">RENTAL #{record.id}</p>
      <h1>Update listing</h1>
      <p>Edit the title and address. The other rental details stay saved.</p>
      <form onSubmit={submit}>
        <fieldset disabled={pending}>
          <TitleFields
            values={values}
            onChange={(event) =>
              setValues((previous) => ({
                ...previous,
                [event.target.name]: event.target.value,
              }))
            }
          />
        </fieldset>
        <ErrorNotice error={error} />
        <FormActions pending={pending} label="Save changes" />
      </form>
    </section>
  );
}

export default function UpdateRecord({ id, onUpdate }) {
  const state = useSelectedRental(id);
  return state.record ? (
    <UpdateForm
      key={state.record.id}
      record={state.record}
      onUpdate={onUpdate}
    />
  ) : (
    <RecordState {...state} />
  );
}
