import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.companies.models import Company, CompanyRole, CompanyUser


async def register_and_login(client: AsyncClient, email: str, name: str = "Test User") -> str:
    """Helper to register and login a user, returning their JWT bearer token."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_resp.json()["access_token"]


@pytest.mark.asyncio
async def test_authenticated_user_can_create_company(async_client: AsyncClient, db_session: AsyncSession):
    """Test that an authenticated user can create a company and automatically becomes OWNER."""
    token = await register_and_login(async_client, "owner@company.com", "Company Owner")

    create_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "SevenCore Technologies"},
    )
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["name"] == "SevenCore Technologies"
    assert data["is_active"] is True
    assert data["role"] == "OWNER"
    assert "id" in data

    # Verify in database
    company_id = data["id"]
    db_company = (await db_session.execute(select(Company).where(Company.id == company_id))).scalars().first()
    assert db_company is not None
    assert db_company.name == "SevenCore Technologies"

    # Verify CompanyUser membership in database
    membership = (
        await db_session.execute(select(CompanyUser).where(CompanyUser.company_id == company_id))
    ).scalars().first()
    assert membership is not None
    assert membership.role == CompanyRole.OWNER.value


@pytest.mark.asyncio
async def test_unauthenticated_user_cannot_create_company(async_client: AsyncClient):
    """Test that unauthenticated requests to create a company are rejected with 401."""
    resp = await async_client.post(
        "/api/v1/companies/",
        json={"name": "Unauthorized Company"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_member_can_retrieve_their_company(async_client: AsyncClient):
    """Test that a member can retrieve company details by ID."""
    token = await register_and_login(async_client, "alice@company.com", "Alice")
    create_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Acme Corp"},
    )
    company_id = create_resp.json()["id"]

    get_resp = await async_client.get(
        f"/api/v1/companies/{company_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == company_id
    assert data["name"] == "Acme Corp"
    assert data["role"] == "OWNER"


@pytest.mark.asyncio
async def test_user_cannot_retrieve_unauthorized_company(async_client: AsyncClient):
    """Test that a user cannot access a company they are not a member of (404 Not Found to prevent enumeration)."""
    # User A creates Company 1
    token_a = await register_and_login(async_client, "usera@company.com", "User A")
    resp_a = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company Alpha"},
    )
    company_1_id = resp_a.json()["id"]

    # User B creates Company 2
    token_b = await register_and_login(async_client, "userb@company.com", "User B")
    await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Company Beta"},
    )

    # User B tries to access Company 1 -> returns 404 to prevent resource enumeration
    unauthorized_resp = await async_client.get(
        f"/api/v1/companies/{company_1_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert unauthorized_resp.status_code == 404
    assert unauthorized_resp.json()["detail"] == "Company not found"


@pytest.mark.asyncio
async def test_company_resource_id_enumeration_mitigation(async_client: AsyncClient):
    """Regression test for FINDING-04: Nonexistent company ID and cross-company unauthorized ID
    produce identical HTTP 404 responses to prevent company resource ID enumeration.
    """
    token_a = await register_and_login(async_client, "owner_enum_a@test.com")
    comp_a_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company Enum A"},
    )
    comp_a_id = comp_a_resp.json()["id"]

    token_b = await register_and_login(async_client, "owner_enum_b@test.com")

    # 1. Nonexistent company ID
    nonexistent_resp = await async_client.get(
        "/api/v1/companies/999999",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert nonexistent_resp.status_code == 404
    assert nonexistent_resp.json() == {"detail": "Company not found"}

    # 2. Existing company belonging to another user (User A)
    cross_company_resp = await async_client.get(
        f"/api/v1/companies/{comp_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_company_resp.status_code == 404
    assert cross_company_resp.json() == {"detail": "Company not found"}

    # Responses are completely indistinguishable
    assert nonexistent_resp.status_code == cross_company_resp.status_code
    assert nonexistent_resp.json() == cross_company_resp.json()

    # 3. Authorized user accessing their own company
    authorized_resp = await async_client.get(
        f"/api/v1/companies/{comp_a_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert authorized_resp.status_code == 200
    assert authorized_resp.json()["id"] == comp_a_id
    assert authorized_resp.json()["name"] == "Company Enum A"


@pytest.mark.asyncio
async def test_company_data_isolation_in_listing(async_client: AsyncClient):
    """Test that listing companies only returns the companies the user belongs to."""
    token_a = await register_and_login(async_client, "user1@company.com", "User 1")
    token_b = await register_and_login(async_client, "user2@company.com", "User 2")

    # User A creates 2 companies
    await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company One"},
    )
    await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company Two"},
    )

    # User B creates 1 company
    await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Company Three"},
    )

    # User A lists companies -> should see exactly 2 companies
    list_a = await async_client.get("/api/v1/companies/", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    names_a = [c["name"] for c in list_a.json()]
    assert sorted(names_a) == ["Company One", "Company Two"]

    # User B lists companies -> should see exactly 1 company
    list_b = await async_client.get("/api/v1/companies/", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    names_b = [c["name"] for c in list_b.json()]
    assert names_b == ["Company Three"]


@pytest.mark.asyncio
async def test_add_company_member_and_duplicate_rejection(async_client: AsyncClient):
    """Test adding a member to a company and rejecting duplicate membership."""
    token_owner = await register_and_login(async_client, "boss@company.com", "Boss")
    await register_and_login(async_client, "worker@company.com", "Worker")

    create_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Collaborative Corp"},
    )
    company_id = create_resp.json()["id"]

    # Add worker as MEMBER
    add_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "worker@company.com", "role": "MEMBER"},
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["email"] == "worker@company.com"
    assert add_resp.json()["role"] == "MEMBER"

    # Attempt to add same worker again -> 409 Conflict
    dup_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "worker@company.com", "role": "MEMBER"},
    )
    assert dup_resp.status_code == 409
    assert dup_resp.json()["detail"] == "User is already a member of this company"


@pytest.mark.asyncio
async def test_nonexistent_company_returns_404(async_client: AsyncClient):
    """Test that requesting a non-existent company ID returns 404 Not Found."""
    token = await register_and_login(async_client, "user_404@company.com")
    resp = await async_client.get(
        "/api/v1/companies/99999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Company not found"


@pytest.mark.asyncio
async def test_update_member_role_and_owner_protection(async_client: AsyncClient, db_session: AsyncSession):
    """Test updating member role between ADMIN and MEMBER, and ensuring OWNER is protected."""
    token_owner = await register_and_login(async_client, "owner_role@company.com", "Owner")
    token_member = await register_and_login(async_client, "member_role@company.com", "Member")
    
    # Create company
    c_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Role Test Co"},
    )
    company_id = c_resp.json()["id"]

    # Add member
    add_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "member_role@company.com", "role": "MEMBER"},
    )
    member_user_id = add_resp.json()["user_id"]

    # 1. Owner promotes Member to ADMIN
    update_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{member_user_id}/role",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"role": "ADMIN"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["role"] == "ADMIN"

    # 2. Promoted Admin cannot change their own role (400 Bad Request)
    demote_self_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{member_user_id}/role",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"role": "MEMBER"},
    )
    assert demote_self_resp.status_code == 400
    assert "cannot change your own role" in demote_self_resp.json()["detail"].lower()

    # Add a second member for Admin to manage
    token_second = await register_and_login(async_client, "second_member@company.com", "Second Member")
    add_second_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "second_member@company.com", "role": "MEMBER"},
    )
    second_user_id = add_second_resp.json()["user_id"]

    # Admin CAN change another permitted member's role
    admin_change_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{second_user_id}/role",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"role": "ADMIN"},
    )
    assert admin_change_resp.status_code == 200
    assert admin_change_resp.json()["role"] == "ADMIN"

    # 3. Regular MEMBER cannot update roles (403 Forbidden)
    forbidden_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{second_user_id}/role",
        headers={"Authorization": f"Bearer {token_second}"}, # token_second was promoted, let's demote back or use third
        json={"role": "MEMBER"},
    )
    # token_second was promoted to admin by admin_change_resp, so demote by owner
    await async_client.put(
        f"/api/v1/companies/{company_id}/members/{second_user_id}/role",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"role": "MEMBER"},
    )
    forbidden_resp2 = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{member_user_id}/role",
        headers={"Authorization": f"Bearer {token_second}"},
        json={"role": "ADMIN"},
    )
    assert forbidden_resp2.status_code == 403

    # 4. Attempt to modify OWNER's role -> 400/403 Forbidden
    members_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    owner_member = next(m for m in members_resp.json() if m["role"] == "OWNER")
    owner_user_id = owner_member["user_id"]

    owner_protect_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}/role",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"role": "ADMIN"},
    )
    assert owner_protect_resp.status_code == 400
    assert "cannot change your own role" in owner_protect_resp.json()["detail"].lower()

    admin_modify_owner_resp = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}/role",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"role": "MEMBER"},
    )
    assert admin_modify_owner_resp.status_code == 403
    assert "Cannot modify the role of the workspace Owner" in admin_modify_owner_resp.json()["detail"]


@pytest.mark.asyncio
async def test_remove_member_and_cleanup_email_access(async_client: AsyncClient, db_session: AsyncSession):
    """Test removing a member, verifying email-account access cleanup while preserving user."""
    from app.modules.auth.models import User
    from app.modules.email_accounts.models import EmailAccountAccess

    token_owner = await register_and_login(async_client, "owner_rm@company.com", "Owner RM")
    token_target = await register_and_login(async_client, "target_rm@company.com", "Target RM")

    # Create company
    c_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Removal Corp"},
    )
    company_id = c_resp.json()["id"]

    # Add target member
    add_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "target_rm@company.com", "role": "MEMBER"},
    )
    target_user_id = add_resp.json()["user_id"]

    # Create email account for company
    acc_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={
            "name": "Support Inbox",
            "email_address": "support@removalcorp.com",
            "provider": "CUSTOM",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "imap_host": "imap.example.com",
            "imap_port": 993,
        },
    )
    assert acc_resp.status_code == 201
    account_id = acc_resp.json()["id"]

    # Grant target user access to this email account
    grant_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/email-accounts/{account_id}/access",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"user_id": target_user_id},
    )
    assert grant_resp.status_code == 201

    # Verify company-wide email accounts access endpoint
    access_list_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts-access",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert access_list_resp.status_code == 200
    accesses = access_list_resp.json()
    assert len(accesses) == 1
    assert accesses[0]["user_id"] == target_user_id
    assert accesses[0]["email_account_id"] == account_id

    # 1. Target member cannot remove other members (403)
    unauth_rm = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{target_user_id}",
        headers={"Authorization": f"Bearer {token_target}"},
    )
    assert unauth_rm.status_code == 403

    # 2. Owner removes target member
    rm_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{target_user_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert rm_resp.status_code == 204

    # 3. Verify member is no longer in company members list
    members_after = await async_client.get(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert all(m["user_id"] != target_user_id for m in members_after.json())

    # 4. Verify explicit EmailAccountAccess was deleted
    access_after = await async_client.get(
        f"/api/v1/companies/{company_id}/email-accounts-access",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert len(access_after.json()) == 0

    # 5. Verify target User record still exists in users table (not deleted)
    user_record = (
        await db_session.execute(select(User).where(User.id == target_user_id))
    ).scalars().first()
    assert user_record is not None
    assert user_record.email == "target_rm@company.com"

    # 6. Verify Owner cannot be removed
    members_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    owner_user_id = next(m["user_id"] for m in members_resp.json() if m["role"] == "OWNER")
    rm_owner_resp = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert rm_owner_resp.status_code in [400, 403]


@pytest.mark.asyncio
async def test_invitation_lifecycle_and_authorization(async_client: AsyncClient, db_session: AsyncSession):
    """Test full invitation lifecycle, authorization rules, acceptance, and decline."""
    # 1. Setup Owner and Company
    token_owner = await register_and_login(async_client, "workspace_owner@test.com", "Workspace Owner")
    resp_co = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Pulse Solutions"},
    )
    assert resp_co.status_code == 201
    company_id = resp_co.json()["id"]

    # 2. Setup prospective invitees
    token_invitee1 = await register_and_login(async_client, "invitee1@test.com", "Invitee One")
    token_invitee2 = await register_and_login(async_client, "invitee2@test.com", "Invitee Two")
    token_outsider = await register_and_login(async_client, "outsider@test.com", "Outsider")

    # 3. Owner creates invitation for invitee1 (MEMBER) and invitee2 (ADMIN)
    inv1_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "invitee1@test.com", "role": "MEMBER"},
    )
    assert inv1_resp.status_code == 201
    inv1_data = inv1_resp.json()
    assert inv1_data["invited_email"] == "invitee1@test.com"
    assert inv1_data["role"] == "MEMBER"
    assert inv1_data["status"] == "PENDING"
    inv1_id = inv1_data["id"]

    inv2_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "invitee2@test.com", "role": "ADMIN"},
    )
    assert inv2_resp.status_code == 201
    inv2_id = inv2_resp.json()["id"]

    # 4. Validation: Cannot invite as OWNER
    bad_role_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "bad_role@test.com", "role": "OWNER"},
    )
    assert bad_role_resp.status_code == 400

    # 5. Validation: Cannot invite existing company member
    dup_member_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "workspace_owner@test.com", "role": "ADMIN"},
    )
    assert dup_member_resp.status_code == 409

    # 6. Validation: Cannot create duplicate pending invitation
    dup_pending_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "invitee1@test.com", "role": "ADMIN"},
    )
    assert dup_pending_resp.status_code == 409

    # 7. Authorization: Outsider cannot invite users to this company
    outsider_invite = await async_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_outsider}"},
        json={"email": "random@test.com", "role": "MEMBER"},
    )
    assert outsider_invite.status_code in (403, 404)

    # 8. Check my-pending invitations
    # Invitee 1 sees inv1
    my_invs_1 = await async_client.get(
        "/api/v1/invitations/my-pending",
        headers={"Authorization": f"Bearer {token_invitee1}"},
    )
    assert my_invs_1.status_code == 200
    invs_list_1 = my_invs_1.json()
    assert len(invs_list_1) == 1
    assert invs_list_1[0]["id"] == inv1_id
    assert invs_list_1[0]["company_name"] == "Pulse Solutions"
    assert invs_list_1[0]["role"] == "MEMBER"

    # Invitee 2 sees inv2, does not see inv1
    my_invs_2 = await async_client.get(
        "/api/v1/invitations/my-pending",
        headers={"Authorization": f"Bearer {token_invitee2}"},
    )
    assert my_invs_2.status_code == 200
    invs_list_2 = my_invs_2.json()
    assert len(invs_list_2) == 1
    assert invs_list_2[0]["id"] == inv2_id
    assert invs_list_2[0]["role"] == "ADMIN"

    # Outsider sees 0 invitations
    my_invs_out = await async_client.get(
        "/api/v1/invitations/my-pending",
        headers={"Authorization": f"Bearer {token_outsider}"},
    )
    assert my_invs_out.status_code == 200
    assert len(my_invs_out.json()) == 0

    # 9. Authorization: Outsider cannot accept or decline Invitee 1's invitation
    bad_accept = await async_client.post(
        f"/api/v1/invitations/{inv1_id}/accept",
        headers={"Authorization": f"Bearer {token_outsider}"},
    )
    assert bad_accept.status_code == 403

    bad_decline = await async_client.post(
        f"/api/v1/invitations/{inv1_id}/decline",
        headers={"Authorization": f"Bearer {token_outsider}"},
    )
    assert bad_decline.status_code == 403

    # 10. Invitee 1 declines their invitation
    dec_resp = await async_client.post(
        f"/api/v1/invitations/{inv1_id}/decline",
        headers={"Authorization": f"Bearer {token_invitee1}"},
    )
    assert dec_resp.status_code == 200
    assert dec_resp.json()["status"] == "DECLINED"

    # Invitee 1 now has 0 pending invitations
    pending_after_dec = await async_client.get(
        "/api/v1/invitations/my-pending",
        headers={"Authorization": f"Bearer {token_invitee1}"},
    )
    assert len(pending_after_dec.json()) == 0

    # Cannot decline or accept already processed invitation
    cannot_dec_again = await async_client.post(
        f"/api/v1/invitations/{inv1_id}/decline",
        headers={"Authorization": f"Bearer {token_invitee1}"},
    )
    assert cannot_dec_again.status_code == 400

    cannot_accept_dec = await async_client.post(
        f"/api/v1/invitations/{inv1_id}/accept",
        headers={"Authorization": f"Bearer {token_invitee1}"},
    )
    assert cannot_accept_dec.status_code == 400

    # Invitee 1 still has no company
    cos_1 = await async_client.get(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_invitee1}"},
    )
    assert len(cos_1.json()) == 0

    # 11. Invitee 2 accepts their invitation
    accept_resp = await async_client.post(
        f"/api/v1/invitations/{inv2_id}/accept",
        headers={"Authorization": f"Bearer {token_invitee2}"},
    )
    assert accept_resp.status_code == 200
    accept_data = accept_resp.json()
    assert accept_data["id"] == company_id
    assert accept_data["name"] == "Pulse Solutions"
    assert accept_data["role"] == "ADMIN"

    # Invitee 2 now belongs to company with role ADMIN
    cos_2 = await async_client.get(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_invitee2}"},
    )
    assert len(cos_2.json()) == 1
    assert cos_2.json()[0]["id"] == company_id
    assert cos_2.json()[0]["role"] == "ADMIN"

    # Invitee 2 now has 0 pending invitations
    pending_after_acc = await async_client.get(
        "/api/v1/invitations/my-pending",
        headers={"Authorization": f"Bearer {token_invitee2}"},
    )
    assert len(pending_after_acc.json()) == 0

    # Cannot accept already accepted invitation
    cannot_acc_again = await async_client.post(
        f"/api/v1/invitations/{inv2_id}/accept",
        headers={"Authorization": f"Bearer {token_invitee2}"},
    )
    assert cannot_acc_again.status_code == 400

    # 12. Invitee 2 is now ADMIN and can invite another user
    token_invitee3 = await register_and_login(async_client, "invitee3@test.com", "Invitee Three")
    admin_inv_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_invitee2}"},
        json={"email": "invitee3@test.com", "role": "MEMBER"},
    )
    assert admin_inv_resp.status_code == 201
    inv3_id = admin_inv_resp.json()["id"]

    # Invitee 3 accepts and becomes MEMBER
    await async_client.post(
        f"/api/v1/invitations/{inv3_id}/accept",
        headers={"Authorization": f"Bearer {token_invitee3}"},
    )

    # Invitee 3 as MEMBER cannot create invitations
    member_inv_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_invitee3}"},
        json={"email": "someone@test.com", "role": "MEMBER"},
    )
    assert member_inv_resp.status_code == 403

    # Company invitations list by Admin
    co_invs_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/invitations",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert co_invs_resp.status_code == 200
    assert len(co_invs_resp.json()) >= 3


@pytest.mark.asyncio
async def test_self_management_protection_and_admin_rules(async_client: AsyncClient, db_session: AsyncSession):
    """Test that ADMIN and OWNER cannot change their own role or remove themselves,
    while permitted management of other members remains intact.
    """
    # 1. Setup Owner and Company
    token_owner = await register_and_login(async_client, "perm_owner@company.com", "Owner User")
    resp_co = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Guardian Technologies"},
    )
    assert resp_co.status_code == 201
    company_id = resp_co.json()["id"]

    # Get Owner's user ID
    members_resp = await async_client.get(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    owner_user_id = next(m["user_id"] for m in members_resp.json() if m["role"] == "OWNER")

    # 2. Add an Admin and a Member
    token_admin = await register_and_login(async_client, "perm_admin@company.com", "Admin User")
    token_member = await register_and_login(async_client, "perm_member@company.com", "Member User")
    token_other = await register_and_login(async_client, "perm_other@company.com", "Other Member")

    add_admin_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "perm_admin@company.com", "role": "ADMIN"},
    )
    assert add_admin_resp.status_code == 201
    admin_user_id = add_admin_resp.json()["user_id"]

    add_member_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "perm_member@company.com", "role": "MEMBER"},
    )
    assert add_member_resp.status_code == 201
    member_user_id = add_member_resp.json()["user_id"]

    add_other_resp = await async_client.post(
        f"/api/v1/companies/{company_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "perm_other@company.com", "role": "MEMBER"},
    )
    assert add_other_resp.status_code == 201
    other_user_id = add_other_resp.json()["user_id"]

    # ---------------------------------------------------------
    # 1. ADMIN cannot change own role
    # ---------------------------------------------------------
    admin_self_role = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{admin_user_id}/role",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"role": "MEMBER"},
    )
    assert admin_self_role.status_code == 400
    assert "cannot change your own role" in admin_self_role.json()["detail"].lower()

    # ---------------------------------------------------------
    # 2. ADMIN cannot remove self
    # ---------------------------------------------------------
    admin_self_remove = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{admin_user_id}",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert admin_self_remove.status_code == 400
    assert "cannot remove yourself" in admin_self_remove.json()["detail"].lower()

    # ---------------------------------------------------------
    # 3. OWNER cannot change own role
    # ---------------------------------------------------------
    owner_self_role = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}/role",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"role": "ADMIN"},
    )
    assert owner_self_role.status_code == 400
    assert "cannot change your own role" in owner_self_role.json()["detail"].lower()

    # ---------------------------------------------------------
    # 4. OWNER cannot remove self
    # ---------------------------------------------------------
    owner_self_remove = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert owner_self_remove.status_code in [400, 403]

    # ---------------------------------------------------------
    # 5. ADMIN can still change another permitted member's role
    # ---------------------------------------------------------
    admin_change_member = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{member_user_id}/role",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"role": "ADMIN"},
    )
    assert admin_change_member.status_code == 200
    assert admin_change_member.json()["role"] == "ADMIN"

    # ---------------------------------------------------------
    # 6. ADMIN can still remove another permitted member
    # ---------------------------------------------------------
    admin_remove_other = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{other_user_id}",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert admin_remove_other.status_code == 204

    # ---------------------------------------------------------
    # 7. ADMIN cannot modify or remove OWNER
    # ---------------------------------------------------------
    admin_modify_owner = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}/role",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"role": "MEMBER"},
    )
    assert admin_modify_owner.status_code == 403

    admin_remove_owner = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{owner_user_id}",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert admin_remove_owner.status_code == 403

    # ---------------------------------------------------------
    # 8. MEMBER still cannot manage members
    # ---------------------------------------------------------
    # Demote member_user back to MEMBER by Owner
    await async_client.put(
        f"/api/v1/companies/{company_id}/members/{member_user_id}/role",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"role": "MEMBER"},
    )

    member_try_role = await async_client.put(
        f"/api/v1/companies/{company_id}/members/{admin_user_id}/role",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"role": "MEMBER"},
    )
    assert member_try_role.status_code == 403

    member_try_remove = await async_client.delete(
        f"/api/v1/companies/{company_id}/members/{admin_user_id}",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert member_try_remove.status_code == 403


# =============================================================================
# M14: Company Settings & Name Update Tests
# =============================================================================

@pytest.mark.asyncio
async def test_update_company_name_as_owner(async_client: AsyncClient):
    """Test that a company OWNER can successfully update the company name."""
    token_owner = await register_and_login(async_client, "owner_update_co@test.com", "Owner User")
    comp_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Original Name Corp"},
    )
    assert comp_resp.status_code == 201
    comp_id = comp_resp.json()["id"]

    # Update company name with whitespace padding to verify trimming
    patch_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "  Renamed Tech Ltd  "},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["id"] == comp_id
    assert data["name"] == "Renamed Tech Ltd"
    assert data["role"] == "OWNER"
    assert data["is_active"] is True

    # Verify retrieval reflects the updated name
    get_resp = await async_client.get(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Renamed Tech Ltd"


@pytest.mark.asyncio
async def test_update_company_name_as_admin(async_client: AsyncClient):
    """Test that a company ADMIN can update the company name."""
    token_owner = await register_and_login(async_client, "owner_co_admin@test.com", "Owner User")
    comp_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Admin Test Workspace"},
    )
    comp_id = comp_resp.json()["id"]

    # Register admin user and add to company as ADMIN
    token_admin = await register_and_login(async_client, "admin_co_user@test.com", "Admin User")
    await async_client.post(
        f"/api/v1/companies/{comp_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "admin_co_user@test.com", "role": "ADMIN"},
    )

    # Admin updates company name
    patch_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"name": "Updated by Admin Inc"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["id"] == comp_id
    assert data["name"] == "Updated by Admin Inc"
    assert data["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_update_company_name_as_member_forbidden(async_client: AsyncClient):
    """Test that a MEMBER receives 403 Forbidden when attempting to update company name."""
    token_owner = await register_and_login(async_client, "owner_co_mem@test.com", "Owner User")
    comp_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Member Protected Workspace"},
    )
    comp_id = comp_resp.json()["id"]

    # Register member and add to company as MEMBER
    token_member = await register_and_login(async_client, "regular_mem_co@test.com", "Member User")
    await async_client.post(
        f"/api/v1/companies/{comp_id}/members",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"email": "regular_mem_co@test.com", "role": "MEMBER"},
    )

    # Member attempts to update name
    patch_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_member}"},
        json={"name": "Hacked Name"},
    )
    assert patch_resp.status_code == 403
    assert "Administrator privileges required" in patch_resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_company_name_unauthorized_not_found(async_client: AsyncClient):
    """Test that non-members and nonexistent companies return 404 (anti-enumeration)."""
    token_owner = await register_and_login(async_client, "owner_isolation_a@test.com", "Owner A")
    comp_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Isolation Company A"},
    )
    comp_id = comp_resp.json()["id"]

    token_outsider = await register_and_login(async_client, "outsider_user@test.com", "Outsider")

    # 1. Nonexistent company ID
    nonexistent_resp = await async_client.patch(
        "/api/v1/companies/999999",
        headers={"Authorization": f"Bearer {token_outsider}"},
        json={"name": "Should Fail"},
    )
    assert nonexistent_resp.status_code == 404
    assert nonexistent_resp.json() == {"detail": "Company not found"}

    # 2. Existing company belonging to another user
    cross_company_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_outsider}"},
        json={"name": "Should Fail"},
    )
    assert cross_company_resp.status_code == 404
    assert cross_company_resp.json() == {"detail": "Company not found"}

    # Must be completely indistinguishable
    assert nonexistent_resp.json() == cross_company_resp.json()


@pytest.mark.asyncio
async def test_update_company_validation_empty_and_whitespace(async_client: AsyncClient):
    """Test that empty string and whitespace-only company names are rejected with 422."""
    token_owner = await register_and_login(async_client, "owner_validation_empty@test.com", "Owner Val")
    comp_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Valid Initial Name"},
    )
    comp_id = comp_resp.json()["id"]

    # Empty string
    empty_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": ""},
    )
    assert empty_resp.status_code == 422

    # Whitespace only
    whitespace_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "     "},
    )
    assert whitespace_resp.status_code == 422


@pytest.mark.asyncio
async def test_update_company_validation_oversized_name(async_client: AsyncClient):
    """Test that company names exceeding 255 characters are rejected with 422."""
    token_owner = await register_and_login(async_client, "owner_validation_oversize@test.com", "Owner Val")
    comp_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Oversize Test Company"},
    )
    comp_id = comp_resp.json()["id"]

    oversized_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "X" * 256},
    )
    assert oversized_resp.status_code == 422


@pytest.mark.asyncio
async def test_update_company_rejects_extra_fields(async_client: AsyncClient):
    """Test that attempting to mutate immutable fields (id, role, is_active) is rejected with 422."""
    token_owner = await register_and_login(async_client, "owner_extra_fields@test.com", "Owner Val")
    comp_resp = await async_client.post(
        "/api/v1/companies/",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Extra Fields Company"},
    )
    comp_id = comp_resp.json()["id"]

    extra_resp = await async_client.patch(
        f"/api/v1/companies/{comp_id}",
        headers={"Authorization": f"Bearer {token_owner}"},
        json={"name": "Valid Name", "is_active": False, "role": "MEMBER", "id": 123},
    )
    assert extra_resp.status_code == 422


