module tb_full_adder;
    reg A, B, Cin;
    wire Sum, Cout;

    // Instantiate the Unit Under Test (UUT)
    full_adder dut (
        .A(A),
        .B(B),
        .Cin(Cin),
        .Sum(Sum),
        .Cout(Cout)
    );

    // Testbench stimulus
    initial begin
        // All 8 possible input combinations
        A = 0; B = 0; Cin = 0; #10 check(0,0,0);
        A = 0; B = 0; Cin = 1; #10 check(0,0,1);
        A = 0; B = 1; Cin = 0; #10 check(0,1,0);
        A = 0; B = 1; Cin = 1; #10 check(0,1,1);
        A = 1; B = 0; Cin = 0; #10 check(1,0,0);
        A = 1; B = 0; Cin = 1; #10 check(1,0,1);
        A = 1; B = 1; Cin = 0; #10 check(1,1,0);
        A = 1; B = 1; Cin = 1; #10 check(1,1,1);

        $display("All tests completed.");
        $finish;
    end

    // Self-checking task
    task check(input A_t, B_t, Cin_t);
        integer exp_sum, exp_cout;
        begin
            exp_sum   = A_t ^ B_t ^ Cin_t;
            exp_cout  = (A_t & B_t) | (Cin_t & (~(A_t ^ B_t)));

            if ((Sum !== exp_sum) || (Cout !== exp_cout)) begin
                $display("FAIL: A=%b B=%b Cin=%b | Sum=%b Cout=%b (expected Sum=%b Cout=%b)",
                         A_t, B_t, Cin_t, Sum, Cout, exp_sum, exp_cout);
                $error("Test vector failed.");
            end else begin
                $display("PASS: A=%b B=%b Cin=%b | Sum=%b Cout=%b",
                         A_t, B_t, Cin_t, Sum, Cout);
            end
        end
    endtask
endmodule