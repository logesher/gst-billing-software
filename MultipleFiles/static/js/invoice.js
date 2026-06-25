// Dynamic invoice items
let itemCounter = 0;

function addItem() {
  itemCounter++;
  const table = document.getElementById('items-table').getElementsByTagName('tbody')[0];
  const row = table.insertRow();
  row.innerHTML = `
    <td><input type="text" name="desc[]" class="form-control" required></td>
    <td><input type="text" name="hsn_code[]" class="form-control" required></td>
    <td>
      <select name="unit[]" class="form-select" required>
        <option value="Nos">Nos</option>
        <option value="Units">Units</option>
        <option value="Kg">Kg</option>
        <option value="Gram">Gram</option>
        <option value="Litre">Litre</option>
        <option value="Meter">Meter</option>
        <option value="Box">Box</option>
      </select>
      <input type="hidden" name="discount[]" class="discount" value="0">
    </td>
    <td><input type="number" name="qty[]" class="form-control qty" min="1" value="1" required onchange="calcTotals()"></td>
    <td><input type="number" name="rate[]" class="form-control rate" step="0.01" required onchange="calcTotals()"></td>
    <td><input type="number" name="cgst_rate[]" class="form-control cgst-rate" value="9" step="0.01" required onchange="calcTotals()"></td>
    <td><input type="number" name="sgst_rate[]" class="form-control sgst-rate" value="9" step="0.01" required onchange="calcTotals()"></td>
    <td><input type="number" name="igst_rate[]" class="form-control igst-rate" value="0" step="0.01" required onchange="calcTotals()"></td>
    <td class="item-total">0.00</td>
    <td><button type="button" class="btn btn-danger btn-sm" onclick="removeRow(this)">Remove</button></td>
  `;
  calcTotals();
}

function removeRow(button) {
  const rows = document.querySelectorAll('#items-table tbody tr');
  if (rows.length > 1) {
    button.closest('tr').remove();
  }
  calcTotals();
}

function calcTotals() {
  let subtotal = 0, cgstTotal = 0, sgstTotal = 0, igstTotal = 0;
  document.querySelectorAll('.qty').forEach((qty, i) => {
    const rate = parseFloat(document.querySelectorAll('.rate')[i].value) || 0;
    const qtyVal = parseFloat(qty.value) || 0;
    const cgst = parseFloat(document.querySelectorAll('.cgst-rate')[i].value) || 0;
    const sgst = parseFloat(document.querySelectorAll('.sgst-rate')[i].value) || 0;
    const igst = parseFloat(document.querySelectorAll('.igst-rate')[i].value) || 0;
    const disc = parseFloat(document.querySelectorAll('.discount')[i].value) || 0;
    let amount = qtyVal * rate * (1 - disc/100);
    let itemCgst = amount * (cgst / 100);
    let itemSgst = amount * (sgst / 100);
    let itemIgst = amount * (igst / 100);
    subtotal += amount;
    cgstTotal += itemCgst;
    sgstTotal += itemSgst;
    igstTotal += itemIgst;
    document.querySelectorAll('.item-total')[i].textContent = (amount + itemCgst + itemSgst + itemIgst).toFixed(2);
  });
  const subtotalEl = document.getElementById('subtotal');
  const cgstEl = document.getElementById('cgst_total');
  const sgstEl = document.getElementById('sgst_total');
  const igstEl = document.getElementById('igst_total');
  const grandEl = document.getElementById('grand_total');
  if (subtotalEl) subtotalEl.value = subtotal.toFixed(2);
  if (cgstEl) cgstEl.value = cgstTotal.toFixed(2);
  if (sgstEl) sgstEl.value = sgstTotal.toFixed(2);
  if (igstEl) igstEl.value = igstTotal.toFixed(2);
  if (grandEl) grandEl.value = (subtotal + cgstTotal + sgstTotal + igstTotal).toFixed(2);
}
