import React from "react";
import { useDispatch, useSelector } from "react-redux";
import { deleteRental } from "../features/rentals/rentalsSlice.js";
import {
  ErrorNotice,
  FormActions,
  RecordState,
  useSelectedRental,
  useSubmission,
} from "../components/forms.jsx";

export default function DeleteRecord({ id }) {
  const dispatch = useDispatch();
  const saving = useSelector((state) => state.rentals.mutations[`record:${id}`]?.status === "pending");
  const state = useSelectedRental(id);
  const { pending, error, submit } = useSubmission(
    () => dispatch(deleteRental(id)).unwrap(),
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
        <FormActions pending={pending || saving} label="Delete listing" danger />
      </form>
    </section>
  );
}
