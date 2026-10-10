document.addEventListener('DOMContentLoaded', () => {
    const num1Input = document.getElementById('num1');
    const num2Input = document.getElementById('num2');
    const resultText = document.getElementById('result-text');
    const errorText = document.getElementById('error-text');

    function calculate(operation) {
        const num1 = parseFloat(num1Input.value);
        const num2 = parseFloat(num2Input.value);
        
        errorText.textContent = '';

        if (isNaN(num1) || isNaN(num2)) {
            errorText.textContent = 'Please enter valid numbers';
            resultText.textContent = '';
            return;
        }

        let result;
        let displayNum1 = num1;
        let displayNum2 = num2;

        switch (operation) {
            case 'add':
                result = num1 + num2;
                break;
            case 'subtract':
                result = num1 - num2;
                break;
            case 'multiply':
                result = num1 * num2;
                break;
            case 'divide':
                if (num2 === 0) {
                    errorText.textContent = 'Error: Cannot divide by zero';
                    resultText.textContent = '';
                    return;
                }
                result = num1 / num2;
                break;
            default:
                return;
        }

        resultText.textContent = `${displayNum1} ${getSymbol(operation)} ${displayNum2} = ${result}`;
    }

    function getSymbol(operation) {
        switch(operation) {
            case 'add': return '+';
            case 'subtract': return '-';
            case 'multiply': return '×';
            case 'divide': return '÷';
            default: return '';
        }
    }

    document.getElementById('add').addEventListener('click', () => calculate('add'));
    document.getElementById('subtract').addEventListener('click', () => calculate('subtract'));
    document.getElementById('multiply').addEventListener('click', () => calculate('multiply'));
    document.getElementById('divide').addEventListener('click', () => calculate('divide'));
});