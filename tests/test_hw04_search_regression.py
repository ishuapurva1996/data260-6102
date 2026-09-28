"""Preserve HW3 Unicode casefold search through the MySQL migration."""
def test_search_preserves_sharp_s_casefold(hw4_logged_in, rental_payload):
    row=hw4_logged_in.post('/api/rentals',json={**rental_payload,'listingTitle':'Straße Garden Flat'}).json()
    result=hw4_logged_in.get('/api/rentals',params={'q':'  STRASSE  '})
    assert result.status_code==200
    assert row['id'] in [r['id'] for r in result.json()]
