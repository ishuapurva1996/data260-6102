# DOMAIN_ID - 6 --> Rental Housing Listings

# Domain Entity
Rental Housing Listing

# Fields

# primary field
- listingTitle
  - Type: text
  - Required: yes
  - Description: Title of the rental listing

# secondary field
- propertyAddress
  - Type: text
  - Required: yes
  - Description: Address of the rental property

# submitter's email
- submitterEmail
  - Type: email
  - Required: yes
  - Description: Email address of the person submitting the listing

# content/description field
- description
  - Type: textarea
  - Required: yes
  - Description: Detailed description of the rental property

# dropdown for category selection
- propertyType
  - Type: dropdown
  - Required: yes
  - Allowed values:
    - apartment
    - house
    - condo
    - townhouse

# terms and conditions
- termsAccepted
  - Type: checkbox
  - Required: yes
  - Label: I agree to the terms and conditions.


# submit button
- Submit
  - Type: button
  - Required: yes
  - Label: Create Rental Listing


## HW4 persistence contract

MySQL database `s6102_rel` stores rentals with auto-increment integer IDs. Create
requires the six fields above; title/address are trimmed and limited to 255
characters, description has at least 26 characters, and termsAccepted must be
Boolean true. Update changes title/address only. The API keeps camelCase names;
database columns use snake_case. `rentals.manager_id` optionally refers to
`property_managers.id` for the Part 3 experiment. Managers are separate from
authentication users. `users` stores normalized unique email and an Argon2
password hash. `sessions` stores an opaque login token, user reference, creation,
absolute expiry and last activity in UTC. See the shared contract for exact routes.
