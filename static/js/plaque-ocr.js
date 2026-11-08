/* Browser-side OCR controls shared by the submit and admin edit pages. */
(function () {
  'use strict';

  window.initPlaqueOcr = function (options) {
    const button = document.getElementById(options.buttonId);
    const cancelButton = document.getElementById(options.cancelButtonId);
    const status = document.getElementById(options.statusId);
    const progress = document.getElementById(options.progressId);
    const insertButton = document.getElementById(options.insertButtonId);
    const description = document.getElementById(options.descriptionId);
    if (!button || !status || !progress || !insertButton || !description) return;

    let worker = null;
    let runId = 0;
    let recognizedText = '';

    function setStatus(message) {
      status.textContent = message;
      status.style.display = message ? 'block' : 'none';
    }

    function stopUi() {
      button.disabled = false;
      button.textContent = 'Run OCR';
      if (cancelButton) cancelButton.style.display = 'none';
    }

    button.addEventListener('click', async function () {
      const thisRun = ++runId;
      recognizedText = '';
      insertButton.style.display = 'none';
      progress.value = 0;
      setStatus('Preparing OCR…');
      button.disabled = true;
      button.textContent = 'Recognizing…';
      if (cancelButton) cancelButton.style.display = 'inline-block';

      try {
        const source = await options.getSource();
        if (!source) throw new Error('Choose or add a plaque image first.');

        if (!window.Tesseract) {
          throw new Error('OCR library did not load. Please reload the page and try again.');
        }

        worker = await Tesseract.createWorker('eng', 1, {
          logger: function (message) {
            if (thisRun !== runId) return;
            if (message.status) {
              const pct = Math.round((message.progress || 0) * 100);
              progress.value = pct;
              setStatus(message.status + (message.progress != null ? ' (' + pct + '%)' : ''));
            }
          }
        });

        const result = await worker.recognize(source);
        if (thisRun !== runId) return;
        recognizedText = (result.data.text || '').trim();
        if (!recognizedText) {
          setStatus('No text was recognized. Try a clearer or higher-resolution image.');
        } else {
          progress.value = 100;
          setStatus('OCR complete. Review the recognized text before inserting it.');
          insertButton.style.display = 'inline-block';
        }
      } catch (error) {
        if (thisRun === runId) {
          setStatus(error && error.message ? error.message : 'OCR failed. Please try again.');
        }
      } finally {
        if (worker && thisRun === runId) {
          const oldWorker = worker;
          worker = null;
          await oldWorker.terminate();
        }
        if (thisRun === runId) stopUi();
      }
    });

    if (cancelButton) {
      cancelButton.addEventListener('click', async function () {
        ++runId;
        const oldWorker = worker;
        worker = null;
        recognizedText = '';
        insertButton.style.display = 'none';
        progress.value = 0;
        stopUi();
        setStatus('OCR cancelled.');
        if (oldWorker) await oldWorker.terminate();
      });
    }

    insertButton.addEventListener('click', function () {
      if (!recognizedText) return;
      description.value = description.value.trim()
        ? description.value.trimEnd() + '\n\n' + recognizedText
        : recognizedText;
      description.focus();
      insertButton.style.display = 'none';
      setStatus('Recognized text inserted. Please proofread it.');
    });
  };
})();
