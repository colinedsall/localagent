module full_adder(
    input  wire A,
    input  wire B,
    input  wire Cin,
    output wire Sum,
    output wire Cout
);

// Sum is the XOR of all three inputs
assign Sum = A ^ B ^ Cin;

// XNOR of A and B
wire xnor_ab = ~(A ^ B);

// Carry-out is (A & B) OR (Cin & (A XNOR B))
assign Cout = (A & B) | (Cin & xnor_ab);

endmodule