{
    "name": "PlutoPrint PDF Engine",
    "summary": """
                Replace wkhtmltopdf with PlutoPrint for QWeb PDF report generation. 
                """,
    "description": """
                This Odoo module replaces the default wkhtmltopdf library with the modern, lightweight PlutoPrint engine for QWeb PDF report generation. This integration is  in developer beta, and not ready for production use. We welcome code, feature contributions, and further testing.

                ** https://github.com/jeevanism/pludooprint **

                **PlutoPrint** is a lightweight and easy-to-use Python library for generating high-quality PDFs and images directly from HTML or XML content. It is based on **PlutoBook**’s robust rendering engine and provides a simple API to convert your HTML into crisp PDF documents or vibrant image files. This makes it ideal for reports, invoices, or visual snapshots.

                **https://pypi.org/project/plutoprint**

                """,
    "version": "18.0.0.0.1",
    "license": "AGPL-3",
    "author": "Jeevanism@CodeWasher",
    "website": "https://www.jeevanism.com",
    "images": ["static/description/icon.png"],
    "depends": ["base","web"],
    "data": [
    ],
    "external_dependencies": {
        "python": ["plutoprint"]
    },
    "installable": True,
    "application": False,
}
