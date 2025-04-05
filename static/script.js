//tab switching & messages hiding
document.addEventListener("DOMContentLoaded", function () {
  // Function to handle tab switching
  function openTab(tabName) {
    const tabs = document.querySelectorAll(".tab");
    const tabContents = document.querySelectorAll(".tab-content");

    // Remove the active class from all tabs and contents
    tabs.forEach((tab) => tab.classList.remove("active"));
    tabContents.forEach((content) => content.classList.remove("active"));

    // Set the clicked tab and content as active
    const activeTab = document.querySelector(`.tab[data-tab='${tabName}']`);
    const activeContent = document.getElementById(tabName);

    if (activeTab) activeTab.classList.add("active");
    if (activeContent) activeContent.classList.add("active");

    // Store the active tab in localStorage
    localStorage.setItem("activeTab", tabName);
  }



  // Add click event listeners for tabs
  const tabs = document.querySelectorAll(".tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", function () {
      const targetTab = this.dataset.tab;
      openTab(targetTab);
    });
  });

  // Function to hide messages
  function hideMessages() {
    const messages = document.querySelectorAll(
      ".tab-content div[style*='color: red'], .tab-content div[style*='color: green']"
    );
    messages.forEach((message) => {
      message.style.display = "none";
    });
  }

  // Auto-hide messages after 5000 ms
  setTimeout(hideMessages, 5000);

  // Hide messages on click anywhere
  document.addEventListener("click", hideMessages);

  // Ensure forms don't auto-submit on page reload
  const forms = document.querySelectorAll("form");
  forms.forEach((form) => {
    form.addEventListener("submit", function (event) {
      if (!form.checkValidity()) {
        event.preventDefault(); // Prevent form submission if not valid
      }
    });
  });

  // Check if the page was reloaded and remove error messages
  if (performance.navigation.type === performance.navigation.TYPE_RELOAD) {
    const messages = document.querySelectorAll(".tab-content div[style]");
    messages.forEach((message) => {
      message.remove(); // Remove all error messages
    });
  }
});


//add roll number range functionality in all the pages

  function addRollNumberRange(containerId, rangePrefix) {
        const container = document.getElementById(containerId);
        const rangeCount = container.children.length + 1;

        const newRange = document.createElement("div");
        newRange.classList.add("form-group", "roll-range");
        newRange.innerHTML = `
    <label for="${rangePrefix}start${rangeCount}">Roll Number Range ${rangeCount} Start:</label>
    <input
      type="number"
      class="form-control"
      name="${rangePrefix}start${rangeCount}"
      required
    />
    <label for="${rangePrefix}end${rangeCount}">Roll Number Range ${rangeCount} End:</label>
    <input
      type="number"
      class="form-control"
      name="${rangePrefix}end${rangeCount}"
      required
    />
    <button type="button" onclick="removeRollNumberRange(this)">Remove</button>
    <br /><br />
  `;
        container.appendChild(newRange);
      }

      // Function to remove a roll number range
      function removeRollNumberRange(button) {
        const rangeToRemove = button.parentElement;
        rangeToRemove.remove();
      }

