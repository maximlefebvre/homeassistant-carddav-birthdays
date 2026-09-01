"""Test bout en bout du client CardDAV contre un faux serveur."""

import asyncio
import base64
import importlib.util
import sys
from pathlib import Path

import aiohttp
from aiohttp import web

_MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "carddav_birthdays" / "carddav.py"
_spec = importlib.util.spec_from_file_location("cdb_carddav", _MODULE)
carddav = importlib.util.module_from_spec(_spec)
sys.modules["cdb_carddav"] = carddav
_spec.loader.exec_module(carddav)

USER, PASSWORD = "AB12345", "app-password"
EXPECTED_AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()

VCARD_1 = """BEGIN:VCARD\r
VERSION:3.0\r
UID:contact-1\r
FN:Renaud Lefebvre\r
BDAY:1987-04-12\r
END:VCARD\r
"""
VCARD_2 = """BEGIN:VCARD\r
VERSION:3.0\r
UID:contact-2\r
FN:Zoé Martin\r
BDAY;VALUE=DATE:19920705\r
END:VCARD\r
"""
VCARD_3 = """BEGIN:VCARD\r
VERSION:3.0\r
UID:contact-3\r
FN:Collègue Sans Date\r
END:VCARD\r
"""
VCARD_4 = """BEGIN:VCARD\r
VERSION:3.0\r
UID:contact-4\r
FN:Client Pro\r
BDAY:--1103\r
END:VCARD\r
"""

MULTISTATUS = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">{}</d:multistatus>'


def _check_auth(request):
    if request.headers.get("Authorization") != EXPECTED_AUTH:
        raise web.HTTPUnauthorized()


def _xml(body):
    return web.Response(text=MULTISTATUS.format(body), status=207, content_type="application/xml")


async def propfind_root(request):
    _check_auth(request)
    return _xml(
        "<d:response><d:href>/</d:href><d:propstat><d:prop>"
        "<d:current-user-principal><d:href>/principals/AB12345/</d:href></d:current-user-principal>"
        "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
    )


async def propfind_principal(request):
    _check_auth(request)
    return _xml(
        "<d:response><d:href>/principals/AB12345/</d:href><d:propstat><d:prop>"
        "<c:addressbook-home-set><d:href>/addressbooks/AB12345/</d:href></c:addressbook-home-set>"
        "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
    )


async def propfind_home(request):
    _check_auth(request)
    return _xml(
        "<d:response><d:href>/addressbooks/AB12345/</d:href><d:propstat><d:prop>"
        "<d:resourcetype><d:collection/></d:resourcetype><d:displayname>Home</d:displayname>"
        "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
        "<d:response><d:href>/addressbooks/AB12345/contacts/</d:href><d:propstat><d:prop>"
        "<d:resourcetype><d:collection/><c:addressbook/></d:resourcetype>"
        "<d:displayname>Contacts</d:displayname>"
        "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
        "<d:response><d:href>/addressbooks/AB12345/pro/</d:href><d:propstat><d:prop>"
        "<d:resourcetype><d:collection/><c:addressbook/></d:resourcetype>"
        "<d:displayname>Pro</d:displayname>"
        "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
    )


async def report_contacts(request):
    """Carnet supportant addressbook-query."""
    _check_auth(request)
    body = ""
    for href, card in (("1.vcf", VCARD_1), ("2.vcf", VCARD_2), ("3.vcf", VCARD_3)):
        body += (
            f"<d:response><d:href>/addressbooks/AB12345/contacts/{href}</d:href>"
            "<d:propstat><d:prop><d:getetag>\"1\"</d:getetag>"
            f"<c:address-data>{card}</c:address-data>"
            "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
        )
    return _xml(body)


async def report_pro(request):
    """Carnet refusant le REPORT : force le repli PROPFIND + GET."""
    _check_auth(request)
    raise web.HTTPBadRequest()


async def propfind_pro(request):
    _check_auth(request)
    return _xml(
        "<d:response><d:href>/addressbooks/AB12345/pro/</d:href></d:response>"
        "<d:response><d:href>/addressbooks/AB12345/pro/4.vcf</d:href></d:response>"
    )


async def get_pro_card(request):
    _check_auth(request)
    return web.Response(text=VCARD_4, content_type="text/vcard")


def build_app():
    app = web.Application()
    app.router.add_route("PROPFIND", "/", propfind_root)
    app.router.add_route("PROPFIND", "/principals/AB12345/", propfind_principal)
    app.router.add_route("PROPFIND", "/addressbooks/AB12345/", propfind_home)
    app.router.add_route("REPORT", "/addressbooks/AB12345/contacts/", report_contacts)
    app.router.add_route("REPORT", "/addressbooks/AB12345/pro/", report_pro)
    app.router.add_route("PROPFIND", "/addressbooks/AB12345/pro/", propfind_pro)
    app.router.add_route("GET", "/addressbooks/AB12345/pro/4.vcf", get_pro_card)
    return app


async def main():
    runner = web.AppRunner(build_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    base = f"http://127.0.0.1:{port}/"

    async with aiohttp.ClientSession() as session:
        client = carddav.CardDavClient(session, base, USER, PASSWORD)
        books = await client.async_discover_addressbooks()
        assert [book.name for book in books] == ["Contacts", "Pro"], books
        assert books[0].url == f"{base}addressbooks/AB12345/contacts/"

        birthdays = await client.async_fetch_birthdays([book.url for book in books])
        got = [(b.uid, b.name, b.month, b.day, b.year) for b in birthdays]
        assert got == [
            ("contact-1", "Renaud Lefebvre", 4, 12, 1987),
            ("contact-2", "Zoé Martin", 7, 5, 1992),
            ("contact-4", "Client Pro", 11, 3, None),
        ], got

        bad = carddav.CardDavClient(session, base, USER, "mauvais")
        try:
            await bad.async_discover_addressbooks()
        except carddav.CardDavAuthError:
            pass
        else:
            raise AssertionError("CardDavAuthError attendue")

    await runner.cleanup()
    print("client CardDAV : OK (découverte, REPORT, repli PROPFIND+GET, auth)")


if __name__ == "__main__":
    asyncio.run(main())
