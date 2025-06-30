# Shopify Connector for ERPNext

**Shopify Connector** integrates your Shopify store with ERPNext to streamline order processing, inventory management, and product synchronization.

---

## 🔧 Features

- **Real-Time Data Sync**  
  Sync products, inventory levels, and orders between ERPNext and Shopify in real-time.

- **Order Management**  
  Automatically imports Shopify orders into ERPNext and creates necessary records like Sales Orders and Delivery Notes.

- **Inventory Sync**  
  Keeps stock levels consistent between your ERP and Shopify store.

- **Product Updates**  
  Easily push product updates from ERPNext to Shopify.

---

## 🚀 Why Use This?

- **Improved Productivity**  
  Manage operations more efficiently with fewer manual interventions.

- **Data Accuracy**  
  Avoid errors by maintaining a single source of truth.

- **Fast Order Fulfillment**  
  Speed up order processing and shipment tracking.

---

## 🛠️ Installation

> Ensure ERPNext is installed and running on your server.

1. Clone the repository into your apps folder:
   ```bash
   cd ~/frappe-bench/apps
   git clone https://github.com/your-repo/shopify_connector.git
   ```

2. Add the app to your site:
   ```bash
   bench --site your-site-name install-app shopify_connector
   ```

3. Run migrations:
   ```bash
   bench --site your-site-name migrate
   ```

---

## ⚙️ Configuration

1. Go to **Shopify Connector Settings** in ERPNext.
2. Fill in your:
   - **Shopify API Key**
   - **Password/Access Token**
   - **Store URL**
   - **ERPNext Warehouse mappings**
3. Enable features like:
   - Product sync
   - Inventory sync
   - Order sync
4. (Optional) Set up scheduler for automatic syncing.

---

## 🔄 Sync Triggers

- Inventory sync is triggered on stock update (`Bin` doctype).
- Order import runs on schedule.
- Product sync can be manual or on item update.

---
