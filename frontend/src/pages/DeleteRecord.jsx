import React from "react";
import {
  ErrorNotice,
  FormActions,
  RecordState,
  useSelectedRental,
  useSubmission,
} from "../components/forms.jsx";

export default function DeleteRecord({ id, onDelete }) {
  const state = useSelectedRental(id);
  const { pending, error, submit } = useSubmission(
    () => onDelete(id),
    "Listing deleted.",
  );
  if (!state.record) return <RecordState {...state} />;
  return (
    <section className="panel form-panel">
      <p className="eyebrow">RENTAL #{state.record.id}</p>
      <h1>Delete listing</h1>
      <p>
        Confirm the rental you want to delete. This action cannot be undone.
      </p>
      <div className="record-summary">
        <h2>{state.record.listingTitle}</h2>
        <p>{state.record.propertyAddress}</p>
      </div>
      <form onSubmit={submit}>
        <ErrorNotice error={error} />
        <FormActions pending={pending} label="Delete listing" danger />
      </form>
    </section>
  );
}
