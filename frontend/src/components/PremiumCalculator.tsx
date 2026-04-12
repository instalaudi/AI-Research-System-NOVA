"use client";
import React, { useState } from 'react';
import { Delete, RotateCcw, Equal, X, Minus, Plus, Divide, Percent, History } from 'lucide-react';
import './PremiumCalculator.css';

export default function PremiumCalculator() {
    const [display, setDisplay] = useState('0');
    const [formula, setFormula] = useState('');
    const [history, setHistory] = useState<string[]>([]);
    const [showHistory, setShowHistory] = useState(false);

    const handleNumber = (num: string) => {
        if (display === 'Error') {
            setDisplay(num === '.' ? '0.' : num);
            return;
        }

        if (num === '.') {
            if (display.includes('.')) return; // Decimal guard
            setDisplay(display + '.');
        } else {
            setDisplay(display === '0' ? num : display + num);
        }
    };

    const handleOperator = (op: string) => {
        if (display === 'Error') return;
        
        // If we already have a formula, calculate the intermediate result (chained operations)
        if (formula) {
            const intermediate = getResult();
            if (intermediate === 'Error') {
                setDisplay('Error');
                setFormula('');
                return;
            }
            setFormula(intermediate + ' ' + op + ' ');
            setDisplay('0');
        } else {
            setFormula(display + ' ' + op + ' ');
            setDisplay('0');
        }
    };

    const getResult = (): string => {
        try {
            if (!formula) return display;
            
            const parts = formula.trim().split(' ');
            const numA = parseFloat(parts[0]);
            const operator = parts[1];
            const numB = parseFloat(display);
            
            if (isNaN(numA) || isNaN(numB)) return 'Error';

            let result = 0;
            switch (operator) {
                case '+': result = numA + numB; break;
                case '-': result = numA - numB; break;
                case '*': result = numA * numB; break;
                case '/': result = numB !== 0 ? numA / numB : NaN; break;
                case '%': result = (numA / 100) * numB; break; // Percentage relative to numA
                default: result = numB;
            }

            return !isNaN(result) && isFinite(result) 
                ? String(Number(result.toFixed(8))) 
                : 'Error';
        } catch (e) {
            return 'Error';
        }
    };

    const calculate = () => {
        if (!formula) return;
        const finalResult = getResult();
        setHistory(prev => [`${formula}${display} = ${finalResult}`, ...prev].slice(0, 10));
        setDisplay(finalResult);
        setFormula('');
    };

    const clear = () => {
        setDisplay('0');
        setFormula('');
    };

    const backspace = () => {
        if (display.length > 1) {
            setDisplay(display.slice(0, -1));
        } else {
            setDisplay('0');
        }
    };

    return (
        <div className="premium-calc-container animate-in fade-in zoom-in duration-700">
            <div className="glass-card">
                {/* Header / Display Section */}
                <div className="calc-header" aria-live="polite" aria-atomic="true">
                    <div className="formula-display" aria-label={`Fórmula actual: ${formula}`}>{formula}</div>
                    <div className="main-display" aria-label={`Resultado: ${display}`}>{display}</div>
                </div>

                {/* Controls Section */}
                <div className="calc-controls">
                    <button onClick={clear} className="btn-secondary" title="Limpiar todo" aria-label="Limpiar todo">AC</button>
                    <button onClick={backspace} className="btn-secondary" title="Borrar" aria-label="Borrar"><Delete size={18} /></button>
                    <button onClick={() => handleOperator('%')} className="btn-secondary" title="Porcentaje" aria-label="Porcentaje">%</button>
                    <button onClick={() => handleOperator('/')} className="btn-accent" title="Dividir" aria-label="Dividir"><Divide size={18} /></button>

                    <button onClick={() => handleNumber('7')} className="btn-number" aria-label="Siete">7</button>
                    <button onClick={() => handleNumber('8')} className="btn-number" aria-label="Ocho">8</button>
                    <button onClick={() => handleNumber('9')} className="btn-number" aria-label="Nueve">9</button>
                    <button onClick={() => handleOperator('*')} className="btn-accent" title="Multiplicar" aria-label="Multiplicar"><X size={18} /></button>

                    <button onClick={() => handleNumber('4')} className="btn-number" aria-label="Cuatro">4</button>
                    <button onClick={() => handleNumber('5')} className="btn-number" aria-label="Cinco">5</button>
                    <button onClick={() => handleNumber('6')} className="btn-number" aria-label="Seis">6</button>
                    <button onClick={() => handleOperator('-')} className="btn-accent" title="Restar" aria-label="Restar"><Minus size={18} /></button>

                    <button onClick={() => handleNumber('1')} className="btn-number" aria-label="Uno">1</button>
                    <button onClick={() => handleNumber('2')} className="btn-number" aria-label="Dos">2</button>
                    <button onClick={() => handleNumber('3')} className="btn-number" aria-label="Tres">3</button>
                    <button onClick={() => handleOperator('+')} className="btn-accent" title="Sumar" aria-label="Sumar"><Plus size={18} /></button>

                    <button onClick={() => setShowHistory(!showHistory)} className="btn-number" title="Mostrar Historial" aria-label="Mostrar Historial"><History size={18} /></button>
                    <button onClick={() => handleNumber('0')} className="btn-number" aria-label="Cero">0</button>
                    <button onClick={() => handleNumber('.')} className="btn-number" aria-label="Punto decimal">.</button>
                    <button onClick={calculate} className="btn-equal" title="Calcular" aria-label="Igual"><Equal size={20} /></button>
                </div>

                {/* History Drawer */}
                {showHistory && (
                    <div className="history-drawer animate-in slide-in-from-bottom duration-300">
                        <div className="history-header">
                            <span>Historial</span>
                            <button onClick={() => setHistory([])} title="Reiniciar historial" aria-label="Reiniciar historial"><RotateCcw size={14} /></button>
                        </div>
                        <div className="history-list">
                            {history.length === 0 ? (
                                <p className="empty-history text-center text-xs text-gray-500 mt-4">Sin registros</p>
                            ) : (
                                history.map((item, i) => (
                                    <div key={i} className="history-item">{item}</div>
                                ))
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Background Glows */}
            <div className="glow-1"></div>
            <div className="glow-2"></div>
        </div>
    );
}
