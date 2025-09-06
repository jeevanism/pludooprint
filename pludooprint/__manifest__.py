{
    "name": "PlutoPrint PDF Engine",
    "summary": """
                    Replace wkhtmltopdf with PlutoPrint for QWeb PDF report.
                    PlutoPrint git repo: https://github.com/plutoprint/plutoprint
                """,
    "version": "17.0.1.0.0",
    "license": "LGPL-3",
    "author": "Jeevanism@CodeWasher",
    "depends": ["web"],
    "data": [
        "views/report_layout_pluto.xml",
    ],
    "external_dependencies": {
        "python": ["plutoprint"]
    },
    "installable": True,
    "application": False,
}