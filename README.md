
# PludooPrint - A PlutoPrint PDF Engine integration with Odoo

This Odoo module replaces the default `wkhtmltopdf` library with the modern, lightweight **PlutoPrint** engine for QWeb PDF report generation.

[PlutoPrint](https://github.com/plutoprint/plutoprint)
 offers a robust and simple API to convert HTML and XML content into high-quality PDFs and images. It's built on the reliable PlutoBook rendering engine, making it an excellent choice for generating reports, invoices, and other documents.



## Why use PlutoPrint?

-   **Fast & Lightweight:** Optimized for performance.
    
-   **High-Quality Rendering:** Produces crisp, professional PDF documents.
    
-   **Modern Engine:** A reliable alternative to `wkhtmltopdf`.
    

----------

## Installation

1.  Clone this repository into your Odoo custom addons path.
    
2.  Install the PlutoPrint Python library in your Odoo environment.
    
    Bash
    
    ```
    pip install plutoprint
    
    ```
    
3.  Restart your Odoo service.
    
4.  Navigate to **Apps** in your Odoo instance, click on **Update Apps List**, and search for "PlutoPrint PDF Engine".
    
5.  Click **Install**.
    

----------

## License

This project is licensed under the **GNU Affero General Public License version 3** (AGPL-3).
For more details, see the `LICENSE` file in the repository.



----------

## Contributions

This module is currently in its **developer beta phase** and is not yet considered production-ready. We welcome and encourage code, feature contributions, and further testing. Please feel free to create a pull request or report issues on the repository's issue tracker.

Author: Jeevanism@CodeWasher

Website: https://www.jeevanism.com

PlutoPrint PyPI: https://pypi.org/project/plutoprint/
