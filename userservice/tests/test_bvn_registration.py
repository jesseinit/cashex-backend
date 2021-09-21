import pytest


# Todo - Test for invalid phone number, existing user,


@pytest.mark.django_db
class TestBVNRegistration:
    def test_bvn_enquiry_success(self, client):
        """
        Test for a succesfull bvn enquiry

        GIVEN: A user enter valid bvn data

        WHEN: the user submits the form

        THEN: their data would be verified and return a success response

        """
        response = client.post(
            "/api/v1/auth/bvn/enquire",
            {"mobile_number": "07036968013", "bvn": "22155258549"},
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_bvn_enquiry_with_invalid_field_inputs(self, client):
        """
        Test for a failed bvn enquiry

        GIVEN: A user enters an invalid bvn data

        WHEN: the user submits the form

        THEN: validation errors and return a failure response

        """
        response = client.post(
            "/api/v1/auth/bvn/enquire",
            {"mobile_number": "11004644831", "bvn": "2215566645"},
            content_type="application/json",
        )

        assert response.status_code == 400
