import React, { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { updateRental } from "../features/rentals/rentalsSlice.js";
import {
  ErrorNotice,
  FormActions,
  RecordState,
  RentalFields,
  rentalFields,
  useManagers,
  useSelectedRental,
  useSubmission,
} from "../components/forms.jsx";

function UpdateForm({ record }) {
  const dispatch = useDispatch();
  const managers = useManagers();
  const saving = useSelector((state) => state.rentals.mutations[`record:${record.id}`]?.status === "pending");
  const [values, setValues] = useState({
    listingTitle: record.listingTitle,
    propertyAddress: record.propertyAddress,
    listingCode: record.listingCode,
    availableUnits: String(record.availableUnits),
    managerId: record.managerId == null ? "" : String(record.managerId),
  });
  const { pending, error, submit } = useSubmission(() => {
    return dispatch(updateRental({ id: record.id, fields: rentalFields(values) })).unwrap();
  }, "Listing updated.");
  return (
    <section className="panel form-panel">
      <p className="eyebrow">RENTAL #{record.id}</p>
      <h1>Update listing</h1>
      <p>Edit the title, address, listing code, available units, and manager.</p>
      <form onSubmit={submit}>
        <fieldset disabled={pending || saving}>
          <RentalFields
            managers={managers}
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
        <FormActions pending={pending || saving} disabled={managers.loading || !!managers.error || !managers.records.length} label="Save changes" />
      </form>
    </section>
  );
}

export default function UpdateRecord({ id }) {
  const state = useSelectedRental(id);
  return state.record ? (
    <UpdateForm
      key={state.record.id}
      record={state.record}
    />
  ) : (
    <RecordState {...state} />
  );
}
