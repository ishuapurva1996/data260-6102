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
